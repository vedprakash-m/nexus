"""Checkpoint persistence tests — task 4.6.

Verifies:
1. Graph compiles with AsyncSqliteSaver checkpointer.
2. After ainvoke(), the SQLite checkpoint DB file exists on disk.
3. State is loadable via aget_state() from the same context.
4. Checkpoint DB survives closing and reopening the async context manager.
5. Independent thread_ids are stored and retrieved independently.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from nexus.graph.planner import build_planning_graph
from tests.test_graph.test_routing import _base_state


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _initial_state(request_id: str) -> tuple[dict, dict]:
    """
    Build a minimal WeekendPlanState + runtime dict for checkpoint tests.

    Tool calls are mocked to raise immediately so the graph never tries to
    reach a real LLM or API — the checkpoint mechanism fires before any node
    executes its real logic.

    Returns (state, runtime) — runtime is passed to build_planning_graph(),
    not stored in state (runtime objects are not JSON-serializable).
    """
    from datetime import date

    mock_registry = MagicMock()
    mock_registry.weather = MagicMock()
    mock_registry.weather.get_forecast = AsyncMock(
        side_effect=RuntimeError("mock — halt execution")
    )
    mock_registry.weather.get_air_quality = AsyncMock(
        side_effect=RuntimeError("mock — halt execution")
    )
    mock_registry.weather.get_daylight_window = AsyncMock(
        side_effect=RuntimeError("mock — halt execution")
    )
    mock_registry.routing = MagicMock()
    mock_registry.activity = MagicMock()
    mock_registry.activity.search_activities = AsyncMock(return_value=([], "static_pnw"))

    # model_router must return an awaitable model
    mock_model = MagicMock()
    mock_model.ainvoke = AsyncMock(side_effect=RuntimeError("mock — halt execution"))
    mock_model.with_structured_output = MagicMock(return_value=mock_model)
    mock_router = MagicMock()
    mock_router.get_model = MagicMock(return_value=mock_model)

    state = _base_state()
    state.update(
        {
            "request_id": request_id,
            "user_intent": "hike this saturday",
            "target_date": date(2026, 4, 19),
        }
    )
    runtime = {
        "model_router": mock_router,
        "tool_registry": mock_registry,
        "nexus_config": MagicMock(),
    }
    return state, runtime


async def _run_until_error(graph: object, initial: dict, thread_id: str) -> None:
    """
    Invoke the graph; swallow expected RuntimeError from mocked tools.

    The checkpoint is written before the first node raises, which is the
    behaviour we are testing.
    """
    thread_config = {"configurable": {"thread_id": thread_id}}
    try:
        await graph.ainvoke(initial, config=thread_config)  # type: ignore[attr-defined]
    except (RuntimeError, Exception):
        pass  # Mocked tools raise — that's intentional


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckpointPersistence:

    async def test_graph_compiles_with_async_sqlite_saver(self):
        """build_planning_graph() accepts an AsyncSqliteSaver without error."""
        with tempfile.TemporaryDirectory() as d:
            db_path = str(Path(d) / "compile_check.db")
            async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
                graph = build_planning_graph(checkpointer=checkpointer)
                assert graph is not None

    async def test_checkpoint_db_created_on_disk(self):
        """
        After ainvoke(), the SQLite checkpoint DB file exists on disk.

        Even though the graph errors early (mocked tools raise), LangGraph
        writes the initial checkpoint entry before executing the first node.
        """
        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "nexus_test.db"
            request_id = "ckpt-disk-001"
            initial, runtime = _initial_state(request_id)

            async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
                graph = build_planning_graph(checkpointer=checkpointer, **runtime)
                await _run_until_error(graph, initial, request_id)

            assert db_path.exists(), f"Checkpoint DB not found at {db_path}"
            assert db_path.stat().st_size > 0, "Checkpoint DB is empty"

    async def test_state_loadable_from_checkpoint(self):
        """
        aget_state() returns a non-None StateSnapshot after a run is started.
        """
        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "nexus_test.db"
            request_id = "ckpt-state-001"
            initial, runtime = _initial_state(request_id)

            async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
                graph = build_planning_graph(checkpointer=checkpointer, **runtime)
                await _run_until_error(graph, initial, request_id)
                thread_config = {"configurable": {"thread_id": request_id}}
                snapshot = await graph.aget_state(thread_config)

            assert snapshot is not None
            assert snapshot.values is not None

    async def test_request_id_stored_in_checkpoint(self):
        """
        The request_id fed into initial state is retrievable from the checkpoint.
        """
        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "nexus_test.db"
            request_id = "ckpt-id-check"
            initial, runtime = _initial_state(request_id)

            async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
                graph = build_planning_graph(checkpointer=checkpointer, **runtime)
                await _run_until_error(graph, initial, request_id)
                thread_config = {"configurable": {"thread_id": request_id}}
                snapshot = await graph.aget_state(thread_config)

            assert snapshot.values is not None
            assert snapshot.values.get("request_id") == request_id

    async def test_checkpoint_survives_context_reopen(self):
        """
        Checkpoint written in one async context is readable after closing and
        reopening the AsyncSqliteSaver — proving disk persistence.
        """
        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "nexus_persist.db"
            request_id = "ckpt-persist-001"
            initial, runtime = _initial_state(request_id)

            # First context: write checkpoint
            async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
                graph = build_planning_graph(checkpointer=checkpointer, **runtime)
                await _run_until_error(graph, initial, request_id)

            # Second context: load from fresh connection (runtime re-injected by closure)
            async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer2:
                graph2 = build_planning_graph(checkpointer=checkpointer2, **runtime)
                thread_config = {"configurable": {"thread_id": request_id}}
                snapshot = await graph2.aget_state(thread_config)

            assert snapshot is not None
            assert snapshot.values is not None
            assert snapshot.values.get("request_id") == request_id

    async def test_independent_thread_ids_are_isolated(self):
        """
        Two invocations with different thread_ids produce independent checkpoints,
        each retrievable by its own thread_id.
        """
        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "nexus_multi.db"
            ids = ["thread-alpha", "thread-beta"]

            async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
                for rid in ids:
                    initial, runtime = _initial_state(rid)
                    graph = build_planning_graph(checkpointer=checkpointer, **runtime)
                    await _run_until_error(graph, initial, rid)

                _, runtime0 = _initial_state("check")
                graph_read = build_planning_graph(checkpointer=checkpointer, **runtime0)
                for rid in ids:
                    thread_config = {"configurable": {"thread_id": rid}}
                    snapshot = await graph_read.aget_state(thread_config)
                    assert snapshot is not None, f"No checkpoint found for {rid}"
                    assert snapshot.values is not None
                    assert snapshot.values.get("request_id") == rid

    async def test_unknown_thread_id_returns_empty_values(self):
        """
        aget_state() on a thread_id that was never run returns a snapshot with
        no values (not an exception) — important for graceful fallback in routes.
        """
        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "nexus_empty.db"
            async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
                graph = build_planning_graph(checkpointer=checkpointer)
                thread_config = {"configurable": {"thread_id": "never-invoked"}}
                snapshot = await graph.aget_state(thread_config)

            # Should not raise; values will be empty dict or None
            assert snapshot is not None
            assert not snapshot.values  # empty dict {} or None — both are falsy

