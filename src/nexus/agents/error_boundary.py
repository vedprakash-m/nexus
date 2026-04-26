"""
`agent_error_boundary` decorator — wraps agent functions with standardized
error handling per Tech §12.4.

Behavior:
- HardConstraintDataUnavailable → re-raise (propagates to graph runner)
- asyncio.TimeoutError          → REJECTED|NEEDS_INFO + failure_type=TIMEOUT
- other exceptions              → REJECTED|NEEDS_INFO + failure_type=INTERNAL_ERROR

Hard-constraint agents: always return REJECTED on failure.
Soft-constraint agents: return NEEDS_INFO on failure (non-blocking).
"""

from __future__ import annotations

import asyncio
import functools
import logging
import traceback
from collections.abc import Callable

from nexus.resilience import AgentFailureType, HardConstraintDataUnavailable
from nexus.state.graph_state import WeekendPlanState
from nexus.state.schemas import AgentVerdict

logger = logging.getLogger(__name__)


def agent_error_boundary(
    agent_name: str,
    *,
    is_hard_constraint: bool,
) -> Callable:
    """
    Decorator factory for agent error handling.

    Usage:
        @agent_error_boundary("meteorology", is_hard_constraint=True)
        async def meteorology_review(state: WeekendPlanState) -> dict:
            ...
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(state: WeekendPlanState) -> dict:
            try:
                return await fn(state)
            except HardConstraintDataUnavailable:
                # Critical — re-raise, let the graph runner handle it
                raise
            except asyncio.TimeoutError as exc:
                logger.error("[%s] Timeout: %s", agent_name, exc)
                return _failure_verdict(
                    agent_name=agent_name,
                    is_hard_constraint=is_hard_constraint,
                    failure_type=AgentFailureType.TIMEOUT,
                    reason=f"Agent timed out: {exc}",
                )
            except __import__("httpx").ConnectError as exc:
                # Ollama crash detection (task 9.6) — port 11434 unreachable
                logger.error("[%s] Ollama connection error: %s", agent_name, exc)
                return _failure_verdict(
                    agent_name=agent_name,
                    is_hard_constraint=is_hard_constraint,
                    failure_type=AgentFailureType.INTERNAL_ERROR,
                    reason="Cannot reach Ollama — check /preflight for system status",
                )
            except Exception as exc:
                logger.error(
                    "[%s] Unexpected error: %s\n%s",
                    agent_name,
                    exc,
                    traceback.format_exc(),
                )
                return _failure_verdict(
                    agent_name=agent_name,
                    is_hard_constraint=is_hard_constraint,
                    failure_type=AgentFailureType.INTERNAL_ERROR,
                    reason=f"Internal error: {type(exc).__name__}",
                )

        return wrapper

    return decorator


def _failure_verdict(
    agent_name: str,
    is_hard_constraint: bool,
    failure_type: AgentFailureType,
    reason: str,
) -> dict:
    """
    Build the state update dict for a failed agent.

    Hard-constraint agents always REJECT on failure.
    Soft-constraint agents return NEEDS_INFO (non-blocking).
    """
    verdict_value = "REJECTED" if is_hard_constraint else "NEEDS_INFO"

    verdict = AgentVerdict(
        agent_name=agent_name,
        verdict=verdict_value,  # type: ignore[arg-type]
        is_hard_constraint=is_hard_constraint,
        confidence=0.0,
        rejection_reason=reason,
        failure_type=failure_type,
    )

    return {
        "current_verdicts": [verdict],
        "negotiation_log": [f"{agent_name}: {verdict_value} ({failure_type.value}) — {reason}"],
    }
