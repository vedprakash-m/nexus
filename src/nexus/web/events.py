"""
WebSocket progress event types for streaming plan progress to browser.

Events are JSON-serializable dicts sent over `ws://127.0.0.1:{port}/ws/plans/{id}`.
"""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    PHASE_CHANGED = "phase_changed"
    AGENT_VERDICT = "agent_verdict"
    PLAN_READY = "plan_ready"
    PLAN_SAVED = "plan_saved"
    ERROR = "error"
    ADD_CONSTRAINT = "add_constraint"


def phase_event(phase: str, message: str) -> dict:
    return {"type": EventType.PHASE_CHANGED, "phase": phase, "message": message}


def verdict_event(agent_name: str, verdict: str, reason: str | None) -> dict:
    """
    Agent verdict event — sanitized for user consumption.

    Note: agent_name is used internally only and NOT included in the
    browser event payload (UX §1.3 — no agent names in UI).
    """
    return {
        "type": EventType.AGENT_VERDICT,
        # Internal: omit agent_name from user-facing payload
        "verdict": verdict,
        "reason": reason,
    }


def plan_ready_event(request_id: str, html_fragment: str) -> dict:
    return {
        "type": EventType.PLAN_READY,
        "request_id": request_id,
        "html": html_fragment,
    }


def error_event(message: str) -> dict:
    return {"type": EventType.ERROR, "message": message}
