# Architecture

## Overview

Nexus is a local-first weekend planning system. A user types an intent; the system runs a multi-agent planning graph powered by LangGraph and Ollama, then presents a plan for human approval. Everything runs on `localhost` — no cloud services required.

---

## Graph Topology

```
START
  │
  ▼
parse_intent          ← Orchestrator: intent → PlanRequirements (LLM)
  │
  ▼
draft_proposal        ← Objective: activity search + propose (LLM)
  │
  ├──[Send]──► review_meteorology   ← deterministic threshold checks
  ├──[Send]──► review_family        ← LLM, LOCKED LOCAL
  ├──[Send]──► review_nutrition     ← LLM
  └──[Send]──► review_logistics     ← deterministic routing checks
                    │
                    ▼
              check_consensus       ← Orchestrator: aggregate verdicts
                    │
          ┌─────────┴───────────┐
       REJECTED             ALL APPROVED
          │                     │
          │ (loop back)          ▼
          └──► draft_proposal  review_safety   ← adversarial veto
                                    │
                              ┌─────┴─────┐
                           UNSAFE       SAFE
                              │           │
                             END    synthesize_plan  ← interrupt_after
                                         │
                                     save_plan
                                         │
                                        END
```

### Node Classification

| Node | Type | Agent | Hard constraint |
|------|------|-------|----------------|
| `parse_intent` | LLM | Orchestrator | No |
| `draft_proposal` | LLM + tools | Objective | No |
| `review_meteorology` | Deterministic | Meteorology | Yes |
| `review_family` | LLM (local only) | Family Coordinator | Yes |
| `review_nutrition` | LLM + tools | Nutritional | Yes |
| `review_logistics` | Deterministic + tools | Logistics | Yes |
| `check_consensus` | Deterministic | Orchestrator | — |
| `review_safety` | Deterministic + tools | Safety | Yes |
| `synthesize_plan` | LLM + templates | Synthesizer | No |
| `save_plan` | I/O | SavePlan | No |

---

## State

`WeekendPlanState` is a `TypedDict` defined in `src/nexus/state/graph_state.py`. It flows through every node.

**Key fields:**

| Field | Type | Reducer |
|-------|------|---------|
| `current_verdicts` | `list[AgentVerdict]` | `merge_verdicts` (replace-by-agent) |
| `proposal_history` | `list[ActivityProposal]` | `append_to_list` |
| `negotiation_log` | `list[str]` | `append_log` (timestamped) |
| `pending_constraints` | `list[str]` | default (replace) |
| `iteration_count` | `int` | default (replace) |

**All state access is via `state["field"]` dict syntax — never dot notation.** (`WeekendPlanState` is a TypedDict, not a Pydantic model.)

---

## Tool Abstraction

```
ToolRegistry
├── weather   → OpenMeteoWeather (implements WeatherTool Protocol)
├── routing   → OSRMRouting      (implements RoutingTool Protocol)
├── activity  → OverpassActivities (implements ActivityTool Protocol)
└── places    → YelpPlaces       (implements PlacesTool Protocol)
```

Each provider implements a Protocol interface. Agents call `tool_registry.weather.get_forecast(...)` — they never import concrete provider classes. Swapping a provider requires only a `ToolRegistry` config change.

**Graceful degradation** (`src/nexus/resilience.py`):

```
live API (3 retries, exponential backoff)
  → stale cache (diskcache stale: prefix, no TTL)
  → hard constraint: raise HardConstraintDataUnavailable
  → soft constraint: return default + DataConfidence.ESTIMATED
```

---

## HITL Design

The graph compiles with `interrupt_after=["synthesize_plan"]`. After the synthesizer writes the plan HTML/Markdown to state, the graph pauses. The browser displays the plan.

- **Approve:** `ainvoke(None, config=thread_config)` — resumes from interrupt, runs `save_plan`
- **Reject:** `aupdate_state(as_node="draft_proposal")` injects feedback + resets verdicts, then `ainvoke(None)` replans from scratch
- **Mid-flight constraint:** `aupdate_state` appends to `pending_constraints`; `check_consensus` drains the queue into `rejection_context` on next iteration

Checkpoints are persisted in `~/.nexus/checkpoints/nexus.db` (SQLite). Server restart does not lose in-progress plans.

---

## LLM Architecture

```
ModelRouter
├── local model:  ChatOllama(model="qwen3:8b", temperature=0.2)
└── cloud model:  optional (configurable)

Routing rules:
- "family_coordinator" → always local (LOCKED_LOCAL_AGENTS)
- all others → local by default; cloud if enabled in config
```

All LLM calls use `.with_structured_output(PydanticModel)` — no JSON parsing, no `eval()`. LLM calls are wrapped with `asyncio.wait_for(coro, timeout=N)` per agent:

| Agent | Timeout |
|-------|---------|
| `parse_intent` | 15s |
| `draft_proposal` | 25s |
| `review_family` | 25s |
| `review_nutrition` | 25s |
| `synthesize_plan` | 15s |

The entire planning run has a 90-second hard cap (`asyncio.wait_for(graph.ainvoke(...), timeout=90)` in `run_planning()`).

---

## Web Layer

```
FastAPI (127.0.0.1:7820 only — never network-exposed)
├── GET  /                      → landing page
├── GET  /preflight             → system health page
├── GET  /setup                 → profile wizard
├── GET  /plan                  → planning page (WebSocket)
├── GET  /plans                 → plan history
├── GET  /plans/{id}            → plan detail
├── POST /api/plans             → start planning
├── POST /api/plans/{id}/approve
├── POST /api/plans/{id}/reject
├── POST /api/plans/{id}/constraint
├── POST /api/plans/{id}/feedback
├── POST /api/setup
├── POST /api/setup/api-keys
├── GET  /api/setup/api-keys/status
├── GET  /api/preflight
└── WS   /ws/plans/{id}        → progress streaming + constraint injection
```

Pages are rendered via Jinja2 (`src/nexus/templates/`). All templates use `StrictUndefined` mode — missing variables raise at render time, not silently produce blank output.

WebSocket event types: `phase_changed`, `agent_verdict`, `plan_ready`, `plan_saved`, `error`, `add_constraint`.

---

## Output Pipeline

```
WeekendPlanState
       │
       ▼
render_plan_html(state, narrative)   → output/html.py
       │
       ├── Jinja2 context builder   → _build_context()
       │    (enforces UX §1.3: no agent names, no scores, no iteration counts)
       │
       └── plan.html.j2             → HTML string in state["output_html"]

render_plan_markdown(state, narrative) → output/markdown.py
       │
       └── plan.md.j2              → Markdown string in state["output_markdown"]

save_approved_plan()
       │
       └── writes state["output_markdown"] to ~/.nexus/plans/{date}-{slug}.md
```

---

## Error Handling

`@agent_error_boundary(agent_name, is_hard_constraint=bool)` wraps every agent:

| Exception | Response |
|-----------|----------|
| `HardConstraintDataUnavailable` | Re-raised → graph runner handles |
| `asyncio.TimeoutError` | `AgentVerdict(verdict="REJECTED", failure_type=TIMEOUT)` for hard; `NEEDS_INFO` for soft |
| `httpx.ConnectError` (port 11434) | `INTERNAL_ERROR` + WebSocket error event + `/preflight` link |
| Other `Exception` | `INTERNAL_ERROR` + log full traceback |

---

## Security Notes

- Server binds to `127.0.0.1` only — no network exposure
- API keys stored in `~/.nexus/.env` — never logged, never returned in GET responses
- `ruamel.yaml` used for `profile.yaml` (comment-preserving round-trip)
- No SQL string interpolation — all stats queries use parameterized statements
- No `eval()`, no `exec()`, no dynamic imports (agent registry uses explicit string→class map)
- Jinja2 `autoescaping=True` for all HTML templates — XSS safe
