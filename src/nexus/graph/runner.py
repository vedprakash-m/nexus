"""
`run_planning()` — entry point that builds the graph, connects checkpointer,
and invokes the graph with an initial state.

Checkpointing enables HITL interrupt/resume: the graph is interrupted after
`synthesize_plan` and waits for human approval before `save_plan` runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from nexus.config import NexusConfig
from nexus.graph.planner import build_planning_graph
from nexus.state.graph_state import WeekendPlanState
from nexus.state.helpers import build_initial_state

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Node names that map to progress events (mirrors progress._KNOWN_NODES)
_PROGRESS_NODES = frozenset(
    [
        "parse_intent",
        "draft_proposal",
        "review_meteorology",
        "review_family",
        "review_nutrition",
        "review_logistics",
        "check_consensus",
        "review_safety",
        "synthesize_plan",
        "save_plan",
    ]
)


async def run_planning(
    intent: str,
    config: NexusConfig,
    progress: Any | None = None,
    request_id: str | None = None,
    target_date: "date | None" = None,
) -> tuple[str, object]:
    """
    Start a new planning run, streaming progress events via *progress*.

    Returns (request_id, compiled_graph) so the caller can resume
    via the checkpointer using `request_id` as `thread_id`.

    The graph is interrupted after `synthesize_plan`. The API layer
    resumes via `ainvoke(None, config={"configurable": {"thread_id": request_id}})`.

    Args:
        request_id: If supplied (from routes.py), the same UUID is used as the
                    LangGraph thread_id so that checkpoint lookups, WebSocket
                    subscriptions, and HTTP approve/reject all reference the same run.
    """
    checkpoint_path = config.paths.checkpoints_dir / "nexus.db"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    # Build initial state from config + intent, forwarding the caller-supplied
    # request_id so the checkpoint thread_id matches what routes.py already
    # returned to the browser.
    initial: WeekendPlanState = build_initial_state(
        user_intent=intent,
        config=config,
        request_id=request_id,
        target_date=target_date,
    )

    # Build runtime services — use server-lifecycle singletons when available
    # (singleton = warm cache shared across runs). Fall back to fresh instances
    # in test context where _lifespan has not run (runtime.tool_registry is None).
    import nexus.runtime as runtime
    from nexus.llm.router import ModelRouter
    from nexus.tools.registry import build_registry

    _model_router = runtime.model_router or ModelRouter(config)
    _tool_registry = runtime.tool_registry or build_registry(config)

    request_id = initial["request_id"]

    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        graph = build_planning_graph(
            checkpointer=checkpointer,
            model_router=_model_router,
            tool_registry=_tool_registry,
            nexus_config=config,
        )
        thread_config = {"configurable": {"thread_id": request_id}}

        async def _stream_with_progress() -> None:
            """Consume astream_events and forward node transitions to *progress*."""
            async for event in graph.astream_events(initial, config=thread_config, version="v2"):
                evt_type: str = event.get("event", "")
                node_name: str = event.get("name", "")

                # ISSUE-13: Handle rejection_decided custom events
                if evt_type == "on_custom_event" and node_name == "rejection_decided":
                    if progress is not None:
                        data = event.get("data", {})
                        await progress.on_rejection_decided(
                            data.get("rejection_reason", ""),
                            data.get("iteration", 1),
                        )
                    continue

                if node_name not in _PROGRESS_NODES:
                    continue
                if progress is not None:
                    if evt_type == "on_chain_start":
                        await progress.on_node_start(node_name)
                    elif evt_type == "on_chain_end":
                        await progress.on_node_complete(node_name)

        # PRD §6.5: 90-second planning time cap (corrected from 900s — ISSUE-06)
        from nexus.resilience import HardConstraintDataUnavailable

        try:
            await asyncio.wait_for(_stream_with_progress(), timeout=90.0)
        except asyncio.TimeoutError:
            logger.error("[runner] Planning timed out after 90s for %s", request_id)
            if progress is not None:
                await progress.on_planning_error(
                    "timeout",
                    "Planning took too long (90s limit). Check that Ollama is running and try a simpler request.",
                )
            return request_id, graph
        except HardConstraintDataUnavailable as _hc_exc:
            # A hard-constraint abort propagated out of astream_events.
            # Emit the user-facing detail directly — do NOT let str(_hc_exc)
            # leak the "Hard constraint data unavailable: …" prefix to the UI.
            logger.error("[runner] Hard constraint abort for %s: %s", request_id, _hc_exc)
            if progress is not None:
                msg = _hc_exc.detail or str(_hc_exc)
                await progress.on_planning_error("hard_constraint", msg)
            return request_id, graph

        # Graph is now interrupted after synthesize_plan. Read output_html and
        # broadcast plan_ready so the browser can redirect to the plan page.
        if progress is not None:
            try:
                snapshot = await graph.aget_state(thread_config)
                state_vals = snapshot.values or {}
                output_html: str | None = state_vals.get("output_html")
                if output_html:
                    await progress.on_plan_ready(output_html)
                else:
                    # Diagnose the specific failure point from state so the user
                    # sees a meaningful message instead of the generic "no output".
                    neg_log = state_vals.get("negotiation_log", [])
                    logger.error(
                        "Planning produced no output for %s. negotiation_log: %s",
                        request_id,
                        neg_log,
                    )
                    if state_vals.get("plan_requirements") is None:
                        msg = (
                            "Intent parsing failed — the local model took too long to understand your request. "
                            "Try a simpler phrase, or check /preflight to confirm Ollama is running."
                        )
                    elif state_vals.get("primary_activity") is None:
                        msg = (
                            "No suitable activity could be found within your constraints. "
                            "Try widening your request (e.g. less specific activity or longer drive time)."
                        )
                    else:
                        msg = (
                            "Planning completed but the output could not be generated. "
                            "Check /preflight to confirm Ollama is running and try again."
                        )
                    await progress.on_planning_error("no_output", msg)
            except Exception as _exc:
                logger.warning("Could not emit plan_ready for %s: %s", request_id, _exc)

        # Task 9.8 — write debug log from final checkpoint state (not initial)
        if config.debug:
            try:
                _snap = await graph.aget_state(thread_config)
                _write_debug_log(request_id, _snap.values or {})
            except Exception as _dbg_exc:
                logger.debug("Debug log write failed: %s", _dbg_exc)

    return request_id, graph


async def get_graph_for_resume(checkpoint_path: Path) -> object:
    """
    Build a graph connected to an existing SQLite checkpoint for HITL resume.

    Used by approve_plan() and reject_plan() in the web routes.
    """
    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        return build_planning_graph(checkpointer=checkpointer)


def _write_debug_log(request_id: str, state: WeekendPlanState) -> None:
    """Write negotiation_log to ~/.nexus/logs/{timestamp}-{request_id}.log (task 9.8)."""
    log_dir = Path.home() / ".nexus" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_path = log_dir / f"{ts}-{request_id}.log"
    payload = {
        "request_id": request_id,
        "timestamp": ts,
        "negotiation_log": state.get("negotiation_log", []),
        "iteration_count": state.get("iteration_count", 0),
    }
    log_path.write_text(json.dumps(payload, indent=2, default=str))
    logger.debug("Debug log written to %s", log_path)
