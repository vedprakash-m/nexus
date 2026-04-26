"""
WebSocket progress broadcaster — Tech §9.3.

`PlanningProgress` sends structured JSON events to connected WebSocket clients
as the LangGraph graph executes. Events are also stored in `_completed` for
replay on reconnect (Tech §9.7).

Each event has a unique `event_id` for client-side deduplication.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from nexus.web.events import EventType
from nexus.web.messages import context_for, message_for

logger = logging.getLogger(__name__)

# Known graph node names — unlisted events are silently ignored
_KNOWN_NODES = frozenset(
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


class PlanningProgress:
    """
    Streams planning progress over WebSocket(s).

    Multiple WebSocket connections may be attached (e.g. page reload).
    Completed events are stored for replay on reconnect.
    """

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        self._websockets: list[WebSocket] = []
        self._completed: list[dict] = []  # All events sent — replayed on reconnect
        self._iteration: int = 1

    # ── WebSocket management ──────────────────────────────────────────────────

    async def attach(self, ws: WebSocket) -> None:
        """Attach a new WebSocket, replaying all completed events."""
        self._websockets.append(ws)
        for event in self._completed:
            await self._send_to(ws, event)

    def detach(self, ws: WebSocket) -> None:
        self._websockets = [w for w in self._websockets if w is not ws]

    # ── Event senders ─────────────────────────────────────────────────────────

    async def on_node_start(self, node_name: str) -> None:
        """Called when a graph node begins execution."""
        if node_name not in _KNOWN_NODES:
            return
        if node_name == "draft_proposal":
            # Each pass through draft_proposal is a new iteration
            self._iteration = max(self._iteration, 1)
        event = self._build(
            EventType.PHASE_CHANGED,
            {
                "phase": node_name,
                "status": "active",
                "message": message_for(node_name, self._iteration),
                "context": context_for(node_name),
            },
        )
        await self._broadcast(event)

    async def on_node_complete(self, node_name: str) -> None:
        """Called when a graph node finishes execution."""
        if node_name not in _KNOWN_NODES:
            return
        completed_iteration = self._iteration
        if node_name == "check_consensus":
            self._iteration += 1  # Next pass is a new iteration
        event = self._build(
            EventType.PHASE_CHANGED,
            {
                "phase": node_name,
                "status": "complete",
                "message": message_for(node_name, completed_iteration),
            },
        )
        await self._broadcast(event)

    async def on_rejection_decided(self, reason: str, iteration: int) -> None:
        """ISSUE-13: Called when check_consensus determines a rejection.

        Broadcasts a PHASE_CHANGED event with context.rejection_reason so the
        browser can render 'That didn't work because: <reason>' before the next
        draft_proposal starts.
        """
        event = self._build(
            EventType.PHASE_CHANGED,
            {
                "phase": "check_consensus",
                "status": "rejected",
                "message": f"Revision needed (iteration {iteration})",
                "context": {"rejection_reason": reason},
            },
        )
        await self._broadcast(event)

    async def on_plan_ready(self, html_fragment: str) -> None:
        """Called when synthesize_plan produces output."""
        event = self._build(
            EventType.PLAN_READY,
            {"request_id": self.request_id, "html": html_fragment},
        )
        await self._broadcast(event)

    async def on_planning_error(self, error_type: str, message: str) -> None:
        """
        Called on unrecoverable failures (Ollama crash, HardConstraintDataUnavailable
        with no fallback, asyncio.CancelledError from stop_planning).

        Error events are stored and replayed on reconnect so the client can
        render the error state and offer a /preflight link.
        WebSocket stays open — client polls for UI state.
        """
        event = self._build(
            EventType.ERROR,
            {"error_type": error_type, "message": message},
        )
        await self._broadcast(event)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build(self, event_type: EventType, payload: dict[str, Any]) -> dict:
        event = {
            "event": str(event_type),
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            **payload,
        }
        self._completed.append(event)
        return event

    async def _broadcast(self, event: dict) -> None:
        dead: list[WebSocket] = []
        text = json.dumps(event)
        for ws in self._websockets:
            try:
                await ws.send_text(text)
            except Exception as exc:
                logger.debug("WebSocket send failed: %s", exc)
                dead.append(ws)
        for ws in dead:
            self.detach(ws)

    @staticmethod
    async def _send_to(ws: WebSocket, event: dict) -> None:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            pass


# ── Registry: one PlanningProgress per request_id ────────────────────────────

_registry: dict[str, PlanningProgress] = {}


def get_or_create(request_id: str) -> PlanningProgress:
    if request_id not in _registry:
        _registry[request_id] = PlanningProgress(request_id)
    return _registry[request_id]


def cleanup(request_id: str) -> None:
    _registry.pop(request_id, None)
