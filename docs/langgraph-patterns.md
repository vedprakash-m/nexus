# LangGraph Patterns in Nexus

This document walks through all 13 LangGraph patterns demonstrated in Nexus, with exact code locations and annotated snippets.

> **Target audience:** LangGraph newcomers who want to see idiomatic patterns in a real production application.

---

## Pattern 1 — StateGraph Construction

**Where:** `src/nexus/graph/planner.py`

```python
from langgraph.graph import StateGraph, START, END
from nexus.state.graph_state import WeekendPlanState

def build_planning_graph(checkpointer=None):
    graph = StateGraph(WeekendPlanState)
    graph.add_node("parse_intent", orchestrator_parse_intent)
    graph.add_node("draft_proposal", objective_draft_proposal)
    # ... 8 more nodes ...
    graph.add_edge(START, "parse_intent")
    # ... edges, conditional edges ...
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_after=["synthesize_plan"],
    )
```

`StateGraph(WeekendPlanState)` binds the graph to a typed TypedDict. Every node receives the current state snapshot and returns a partial dict — LangGraph merges the partial update into the full state.

---

## Pattern 2 — Typed State

**Where:** `src/nexus/state/graph_state.py`

```python
from typing import TypedDict, Annotated
from nexus.state.reducers import merge_verdicts, append_to_list, append_log
from nexus.state.schemas import AgentVerdict, ActivityProposal

class WeekendPlanState(TypedDict):
    request_id: str
    primary_activity: ActivityProposal | None
    current_verdicts: Annotated[list[AgentVerdict], merge_verdicts]
    proposal_history: Annotated[list[ActivityProposal], append_to_list]
    negotiation_log: Annotated[list[str], append_log]
    iteration_count: int
    # ... 20 more fields ...
```

Typed state provides:
- IDE autocompletion in agent functions
- Pyright strict-mode validation (any agent with wrong field access is caught at typecheck time)
- Self-documenting graph topology (the TypedDict is the contract between nodes)

---

## Pattern 3 — Reducers

**Where:** `src/nexus/state/reducers.py`

```python
def merge_verdicts(
    existing: list[AgentVerdict],
    update: list[AgentVerdict] | AgentVerdict,
) -> list[AgentVerdict]:
    """Replace verdict by agent_name; append if new agent."""
    updates = [update] if isinstance(update, AgentVerdict) else update
    merged = {v.agent_name: v for v in existing}
    for verdict in updates:
        merged[verdict.agent_name] = verdict
    return list(merged.values())
```

`merge_verdicts` is the reducer for `current_verdicts`. When multiple agents run in parallel (Pattern 6) and each returns `{"current_verdicts": [my_verdict]}`, LangGraph calls `merge_verdicts(existing, new)` for each. The result: one verdict per agent, last write wins per agent name — idempotent on retry.

`append_to_list` simply extends the list. `append_log` adds a timestamp prefix.

---

## Pattern 4 — Conditional Edges

**Where:** `src/nexus/graph/planner.py`

```python
graph.add_conditional_edges(
    "check_consensus",
    route_after_consensus,
    {
        "review_safety": "review_safety",
        "draft_proposal": "draft_proposal",  # loop back
        END: END,                             # critical failure
    },
)
```

`route_after_consensus` inspects state and returns a string key. LangGraph follows the matching edge. The `draft_proposal` → `check_consensus` → `draft_proposal` path is how the cyclical revision loop (Pattern 5) is implemented — there are no explicit loop constructs, just conditional edges pointing backward.

---

## Pattern 5 — Cyclical Loop

**Where:** `src/nexus/graph/planner.py` (routing), `src/nexus/agents/orchestrator.py` (loop control)

The planning graph contains a feedback cycle:

```
draft_proposal ──► [4 reviewers] ──► check_consensus
        ▲                                   │
        └── verdict: REJECTED ───────────────┘
```

Loop termination is enforced in `route_after_consensus`:

```python
def route_after_consensus(state: WeekendPlanState) -> str:
    if state["iteration_count"] >= state["max_iterations"]:
        return "review_safety"  # force best effort through
    if _has_rejection(state["current_verdicts"]):
        return "draft_proposal"  # loop back
    return "review_safety"      # consensus reached
```

`max_iterations` defaults to 3 (configurable in `profile.yaml`). Every loop-back increments `iteration_count` in `orchestrator_check_consensus`.

---

## Pattern 6 — Send API Fan-out (Parallel Execution)

**Where:** `src/nexus/graph/planner.py`

```python
from langgraph.types import Send

def fan_out_to_reviewers(state: WeekendPlanState) -> list[Send]:
    """Dispatch 4 reviewer agents in parallel."""
    return [
        Send("review_meteorology", state),
        Send("review_family",      state),
        Send("review_nutrition",   state),
        Send("review_logistics",   state),
    ]

graph.add_conditional_edges("draft_proposal", fan_out_to_reviewers)
```

**Critical:** returning bare node name strings (`["review_meteorology", ...]`) does NOT produce parallel execution — each would run sequentially and the state snapshots would conflict. `Send` objects carry the current state snapshot so each agent branch sees the same consistent starting state. LangGraph executes all 4 branches concurrently using `asyncio`.

The `merge_verdicts` reducer (Pattern 3) safely merges the 4 concurrent verdict writes.

---

## Pattern 7 — SqliteSaver (Persistence)

**Where:** `src/nexus/graph/runner.py`

```python
from langgraph.checkpoint.sqlite import SqliteSaver

async def run_planning(intent: str, config: NexusConfig) -> tuple[str, object]:
    checkpoint_path = config.paths.checkpoints_dir / "nexus.db"

    with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        graph = build_planning_graph(checkpointer=checkpointer)
        thread_config = {"configurable": {"thread_id": request_id}}
        await asyncio.wait_for(
            graph.ainvoke(initial, config=thread_config),
            timeout=90.0,
        )
```

Each planning run uses `request_id` as `thread_id`. LangGraph checkpoints state after every node. If the server restarts mid-planning, the graph can resume from the last checkpoint — the partial state is never lost.

---

## Pattern 8 — interrupt_after

**Where:** `src/nexus/graph/planner.py`

```python
return graph.compile(
    checkpointer=checkpointer,
    interrupt_after=["synthesize_plan"],
)
```

After `synthesize_plan` writes `output_html` to state, the graph pauses and waits for human input. The API endpoint returns immediately with a `request_id`. The browser displays the plan. The interrupt is persisted via SqliteSaver — the server can restart and the plan is still there waiting.

---

## Pattern 9 — Resume from Interrupt (HITL)

**Where:** `src/nexus/web/routes.py — approve_plan()`

```python
@router.post("/api/plans/{request_id}/approve")
async def approve_plan(request_id: str, ...):
    checkpoint_path = config.paths.checkpoints_dir / "nexus.db"

    with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        graph = build_planning_graph(checkpointer=checkpointer)
        thread_config = {"configurable": {"thread_id": request_id}}
        # Resume from the interrupt point — ainvoke(None) continues from where it stopped
        await graph.ainvoke(None, config=thread_config)
```

`ainvoke(None, config=thread_config)` tells LangGraph: "continue the thread that was interrupted, using the existing checkpoint state." `save_plan` then runs and writes the Markdown file.

**Rejection (re-plan from scratch):**

```python
# Inject feedback and reset planning state
await graph.aupdate_state(
    thread_config,
    {"human_feedback": feedback_text, "iteration_count": 0, "current_verdicts": []},
    as_node="draft_proposal",
)
await graph.ainvoke(None, config=thread_config)
```

`aupdate_state(as_node="draft_proposal")` resumes as if `draft_proposal` had just returned those values — effectively rewinding to the start of the review cycle with fresh context.

---

## Pattern 10 — Supervisor / Worker Architecture

**Where:** `src/nexus/graph/planner.py` (topology), `src/nexus/agents/orchestrator.py` (supervisor)

The orchestrator functions as the supervisor:

- `orchestrator_parse_intent`: translates user intent → structured `PlanRequirements`
- `orchestrator_check_consensus`: aggregates 4 worker verdicts → routing decision + negotiation log entry

The 4 reviewer agents are workers: each evaluates one domain (weather, family, nutrition, logistics) and returns a single `AgentVerdict`. They have no awareness of each other — the supervisor orchestrates.

---

## Pattern 11 — Adversarial Review

**Where:** `src/nexus/graph/planner.py` (structure), `src/nexus/agents/safety.py` (implementation)

`review_safety` runs after consensus is reached by all 4 agents. It is deliberately adversarial — it can veto any plan that the other agents have already approved:

```python
graph.add_conditional_edges(
    "review_safety",
    route_after_safety,
    {"safe": "synthesize_plan", "unsafe": END},
)
```

Safety checks post-sunset return time, hospital proximity, cell coverage, and composite weather+family+remoteness risk — none of which the other agents evaluate. This separation of concerns means a plan can pass weather, logistics, nutrition, and family review but still be blocked by safety.

---

## Pattern 12 — Tool Binding

**Where:** `src/nexus/tools/registry.py`, `src/nexus/runtime.py`

Tools are initialized at server startup and injected as a singleton:

```python
# runtime.py
tool_registry: ToolRegistry | None = None

# server.py lifespan
async def _lifespan(app):
    runtime.tool_registry = ToolRegistry(config)
    runtime.model_router = ModelRouter(config)
    yield

# Any agent
from nexus.runtime import tool_registry

forecast = await tool_registry.weather.get_forecast(...)
```

Each tool implements a Protocol interface (`WeatherTool`, `ActivityTool`, etc.) so agents are decoupled from specific provider implementations. Swapping Overpass for Google Places requires only a `ToolRegistry` config change — no agent code changes.

---

## Pattern 13 — Structured Output

**Where:** `src/nexus/agents/orchestrator.py`, `src/nexus/agents/objective.py`, `src/nexus/agents/family_coordinator.py`, `src/nexus/agents/nutritional.py`

LLM agents use `.with_structured_output()` to guarantee type-safe responses:

```python
# orchestrator.py
from nexus.state.schemas import PlanRequirements
from nexus.runtime import model_router

model = model_router.get_model("orchestrator")
structured_llm = model.with_structured_output(PlanRequirements)

result: PlanRequirements = await asyncio.wait_for(
    structured_llm.ainvoke(prompt),
    timeout=15.0,
)
# result is a Pydantic model — no JSON parsing, no field access errors
return {"plan_requirements": result, ...}
```

`family_coordinator` uses `FamilyPlanVerdict` and `nutritional` uses `NutritionalVerdict` — both have a `.to_agent_verdict()` method that converts to the standard `AgentVerdict` type consumed by the reducer.

`synthesizer` uses plain `ainvoke()` (not structured output) because it generates narrative prose — free text that gets passed directly to the Jinja2 template renderer.

---

## Summary Table

| # | Pattern | Location | Key API |
|---|---------|----------|---------|
| 1 | StateGraph construction | `graph/planner.py` | `StateGraph`, `add_node`, `add_edge`, `compile` |
| 2 | Typed state | `state/graph_state.py` | `TypedDict`, `Annotated` |
| 3 | Reducers | `state/reducers.py` | Custom reducer functions |
| 4 | Conditional edges | `graph/planner.py` | `add_conditional_edges` |
| 5 | Cyclical loop | `graph/planner.py` | Backward conditional edge |
| 6 | Send API fan-out | `graph/planner.py` | `Send` from `langgraph.types` |
| 7 | SqliteSaver persistence | `graph/runner.py` | `SqliteSaver.from_conn_string` |
| 8 | interrupt_after | `graph/planner.py` | `compile(interrupt_after=[...])` |
| 9 | Resume from interrupt | `web/routes.py — approve_plan()` | `ainvoke(None)`, `aupdate_state` |
| 10 | Supervisor / worker | `agents/orchestrator.py` | Separate orchestrator + reviewer nodes |
| 11 | Adversarial review | `agents/safety.py` | Post-consensus veto node |
| 12 | Tool binding | `tools/registry.py` | Protocol interfaces + singleton injection |
| 13 | Structured output | `agents/orchestrator.py` | `.with_structured_output(PydanticModel)` |
