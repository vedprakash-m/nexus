"""
LangGraph planning graph — `build_planning_graph()`.

Phase 9.1: real agent implementations are wired in via the _AGENT_REGISTRY.
Stubs are kept for test isolation — tests that need them can use
`register_agent()` to swap back or build the graph with `use_stubs=True`.

Graph topology (Tech §4.1):
    START
      → parse_intent
      → draft_proposal
      → [fan_out] review_meteorology, review_family, review_nutrition, review_logistics
      → check_consensus
      → (conditional)
            all_approved / max_iterations → review_safety
            has_rejection               → draft_proposal (re-draft loop)
            critical_failure            → END
      → review_safety
      → (conditional)
            safe   → synthesize_plan
            unsafe → END
      → synthesize_plan   [interrupt_after here for HITL]
      → save_plan
      → END
"""

from __future__ import annotations

import functools
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from nexus.state.graph_state import WeekendPlanState
from nexus.state.helpers import (
    all_agents_approved,
    has_critical_safety_rejection,
)
from nexus.state.schemas import AgentVerdict

# ─────────────────────────────────────────────────────────────────────────────
# Stub agents (kept for unit test isolation)
# ─────────────────────────────────────────────────────────────────────────────


async def _stub_parse_intent(state: WeekendPlanState) -> dict:
    return {}


async def _stub_draft_proposal(state: WeekendPlanState) -> dict:
    return {}


async def _stub_review_meteorology(state: WeekendPlanState) -> dict:
    return {}


async def _stub_review_family(state: WeekendPlanState) -> dict:
    return {}


async def _stub_review_nutrition(state: WeekendPlanState) -> dict:
    return {}


async def _stub_review_logistics(state: WeekendPlanState) -> dict:
    return {}


async def _stub_check_consensus(state: WeekendPlanState) -> dict:
    return {}


async def _stub_review_safety(state: WeekendPlanState) -> dict:
    return {}


async def _stub_synthesize_plan(state: WeekendPlanState) -> dict:
    return {}


async def _stub_save_plan(state: WeekendPlanState) -> dict:
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Real agent imports (task 9.1)
# ─────────────────────────────────────────────────────────────────────────────

def _load_real_agents() -> dict:
    """Import real agent implementations. Called once at module load."""
    from nexus.agents.family_coordinator import family_coordinator_review
    from nexus.agents.logistics import logistics_review
    from nexus.agents.meteorology import meteorology_review
    from nexus.agents.nutritional import nutritional_review
    from nexus.agents.objective import objective_draft_proposal
    from nexus.agents.orchestrator import (
        orchestrator_check_consensus,
        orchestrator_parse_intent,
    )
    from nexus.agents.safety import safety_review
    from nexus.agents.save_plan import save_approved_plan
    from nexus.agents.synthesizer import plan_synthesizer

    return {
        "parse_intent": orchestrator_parse_intent,
        "draft_proposal": objective_draft_proposal,
        "review_meteorology": meteorology_review,
        "review_family": family_coordinator_review,
        "review_nutrition": nutritional_review,
        "review_logistics": logistics_review,
        "check_consensus": orchestrator_check_consensus,
        "review_safety": safety_review,
        "synthesize_plan": plan_synthesizer,
        "save_plan": save_approved_plan,
    }


# Module-level registry — populated with real agents on import
_AGENT_REGISTRY: dict[str, object] = _load_real_agents()


def fan_out_to_reviewers(state: WeekendPlanState) -> list[Send] | str:
    """Fan out to all 4 reviewers in parallel via Send objects.

    ISSUE-01: Short-circuit to synthesize_plan when static_template fallback is active.
    Template activities have fabricated coordinates — running them through Logistics
    (OSRM routes) and Safety (emergency-service proximity) produces formally correct
    but semantically meaningless verdicts at the cost of 3-4 LLM calls.
    """
    if state.get("activity_data_source") == "static_template":
        # Skip all reviewer + consensus nodes; synthesizer adds a degraded-data note
        return "synthesize_plan"
    return [
        Send("review_meteorology", state),
        Send("review_family", state),
        Send("review_nutrition", state),
        Send("review_logistics", state),
    ]


def route_after_consensus(state: WeekendPlanState) -> str:
    """
    Routing logic after check_consensus node.

    Priority order (Tech §4.1):
    1. Critical safety rejection (hard constraint + DATA_UNAVAILABLE) → END
    2. Max iterations hit → review_safety (force-advance, skip re-draft)
    3. All agents approved (APPROVED or NEEDS_INFO) → review_safety
    4. Any hard REJECTED → draft_proposal (re-draft loop)
    5. Soft rejection only → draft_proposal

    NEEDS_INFO pass-through (REC-5): NEEDS_INFO alone does not block consensus.
    An agent returning NEEDS_INFO is treated as soft-approved.
    """
    if has_critical_safety_rejection(state):
        return END

    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 3)

    if iteration_count >= max_iterations:
        # Force advance to safety review — let safety make the final call
        return "review_safety"

    if all_agents_approved(state):
        return "review_safety"

    # Any rejection (hard or soft) → re-draft
    return "draft_proposal"


def route_after_safety(state: WeekendPlanState) -> str:
    """
    Route after safety_review node.

    Returns "safe" → synthesize_plan
    Returns "unsafe" → END (hard stop — non-negotiable)
    """
    verdicts: list[AgentVerdict] = state.get("current_verdicts", [])
    for verdict in verdicts:
        if verdict.agent_name == "safety" and verdict.verdict == "REJECTED":
            return "unsafe"
    return "safe"


# ─────────────────────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────────────────────


def build_planning_graph(
    checkpointer: AsyncSqliteSaver | None = None,
    model_router: Any | None = None,
    tool_registry: Any | None = None,
    nexus_config: Any | None = None,
) -> object:
    """
    Build and compile the Nexus planning StateGraph.

    Args:
        checkpointer: AsyncSqliteSaver instance for HITL interrupt/resume support.
                      If None, graph compiles without checkpointing (for tests).
        model_router:  ModelRouter instance — injected into state before each node call.
        tool_registry: ToolRegistry instance — injected into state before each node call.
        nexus_config:  NexusConfig instance — injected into state before each node call.

    Runtime objects (model_router, tool_registry, nexus_config) are NOT stored in
    LangGraph state because they are not JSON-serializable and would be lost on
    checkpoint round-trips. Instead, each node is wrapped with _inject_runtime()
    which merges them into state immediately before calling the agent function.

    Returns:
        Compiled LangGraph graph (CompiledStateGraph).
    """
    # Build the runtime injection dict once — only include non-None values
    _runtime: dict[str, Any] = {}
    if model_router is not None:
        _runtime["model_router"] = model_router
    if tool_registry is not None:
        _runtime["tool_registry"] = tool_registry
    if nexus_config is not None:
        _runtime["config"] = nexus_config

    def _inject_runtime(agent_fn: Any) -> Any:
        """Wrap agent_fn so runtime objects appear in state on every call."""
        if not _runtime:
            return agent_fn  # nothing to inject — skip wrapper overhead

        @functools.wraps(agent_fn)
        async def _wrapper(state: Any) -> dict:
            return await agent_fn({**state, **_runtime})

        return _wrapper
    graph = StateGraph(WeekendPlanState)

    # ── Nodes — each wrapped to inject non-serializable runtime objects ────
    graph.add_node("parse_intent",        _inject_runtime(_AGENT_REGISTRY["parse_intent"]))
    graph.add_node("draft_proposal",      _inject_runtime(_AGENT_REGISTRY["draft_proposal"]))
    graph.add_node("review_meteorology",  _inject_runtime(_AGENT_REGISTRY["review_meteorology"]))
    graph.add_node("review_family",       _inject_runtime(_AGENT_REGISTRY["review_family"]))
    graph.add_node("review_nutrition",    _inject_runtime(_AGENT_REGISTRY["review_nutrition"]))
    graph.add_node("review_logistics",    _inject_runtime(_AGENT_REGISTRY["review_logistics"]))
    graph.add_node("check_consensus",     _inject_runtime(_AGENT_REGISTRY["check_consensus"]))
    graph.add_node("review_safety",       _inject_runtime(_AGENT_REGISTRY["review_safety"]))
    graph.add_node("synthesize_plan",     _inject_runtime(_AGENT_REGISTRY["synthesize_plan"]))
    graph.add_node("save_plan",           _inject_runtime(_AGENT_REGISTRY["save_plan"]))

    # ── Edges ──────────────────────────────────────────────────────────────
    graph.add_edge(START, "parse_intent")
    graph.add_edge("parse_intent", "draft_proposal")

    # Fan-out: draft_proposal → [4 reviewers] in parallel OR direct to synthesize_plan
    graph.add_conditional_edges(
        "draft_proposal",
        fan_out_to_reviewers,
        {
            "review_meteorology": "review_meteorology",
            "review_family": "review_family",
            "review_nutrition": "review_nutrition",
            "review_logistics": "review_logistics",
            "synthesize_plan": "synthesize_plan",  # ISSUE-01: static_template short-circuit
        },
    )

    # All reviewers converge at check_consensus
    graph.add_edge("review_meteorology", "check_consensus")
    graph.add_edge("review_family", "check_consensus")
    graph.add_edge("review_nutrition", "check_consensus")
    graph.add_edge("review_logistics", "check_consensus")

    # Consensus → route (re-draft loop or advance)
    graph.add_conditional_edges(
        "check_consensus",
        route_after_consensus,
        ["draft_proposal", "review_safety", END],
    )

    # Safety → synthesize or END
    graph.add_conditional_edges(
        "review_safety",
        route_after_safety,
        {"safe": "synthesize_plan", "unsafe": END},
    )

    # Linear tail: synthesize → save → END
    graph.add_edge("synthesize_plan", "save_plan")
    graph.add_edge("save_plan", END)

    # ── Compile ────────────────────────────────────────────────────────────
    compile_kwargs: dict = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
        compile_kwargs["interrupt_after"] = ["synthesize_plan"]

    return graph.compile(**compile_kwargs)


def register_agent(node_name: str, agent_fn: object) -> None:
    """
    Replace a stub agent with a real implementation (used in task 9.1).

    This mutates the module-level registry. Call before building the graph.
    """
    if node_name not in _AGENT_REGISTRY:
        raise KeyError(f"Unknown node: {node_name}. Valid nodes: {list(_AGENT_REGISTRY.keys())}")
    _AGENT_REGISTRY[node_name] = agent_fn
