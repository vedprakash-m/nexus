"""
LangGraph state reducers for WeekendPlanState.

Reducers control how concurrent agent writes are merged into shared state.
Each reducer is a function: (existing_value, new_value) -> merged_value.
"""

from __future__ import annotations

from datetime import datetime, timezone

from nexus.state.schemas import AgentVerdict


def merge_verdicts(
    existing: list[AgentVerdict], new: list[AgentVerdict] | AgentVerdict
) -> list[AgentVerdict]:
    """
    Merge new agent verdicts into the existing list.

    Replace-by-agent-name semantics: if a verdict from the same agent_name
    already exists, replace it with the new one. Otherwise append.

    This ensures that when an agent runs multiple times (loop iterations),
    only the most recent verdict from each agent is kept.

    LangGraph Pattern: State reducers handle concurrent writes from
    parallel fan-out nodes. All four review agents write to
    current_verdicts simultaneously; this reducer merges them safely.

    Idempotency: applying the same verdict twice has no additional effect.
    """
    if isinstance(new, AgentVerdict):
        new = [new]

    existing_by_name = {v.agent_name: v for v in existing}
    for verdict in new:
        existing_by_name[verdict.agent_name] = verdict

    return list(existing_by_name.values())


def append_to_list(existing: list, new: list | object) -> list:
    """
    Append new items to a list.

    Handles both single items and lists for flexibility.
    """
    if isinstance(new, list):
        return existing + new
    return existing + [new]


def append_log(existing: list[str], new: list[str] | str) -> list[str]:
    """
    Append timestamped log entries.

    Each entry gets an ISO 8601 timestamp prefix for chronological ordering
    when the debug log is written (task 9.8).
    """
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

    if isinstance(new, str):
        new = [new]

    timestamped = [f"[{timestamp}] {entry}" for entry in new]
    return existing + timestamped
