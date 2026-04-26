"""
Deterministic tests for logistics_review() agent — tasks 5.6 / 5.15.

All tests use mock routing tool — no real OSRM / network calls.
Exact verdict assertions (not LLM text).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock


from tests.test_agents.test_meteorology import _make_proposal, _make_state


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_route(duration_minutes: float, distance_miles: float = 10.0) -> Any:
    from nexus.tools.models import RouteResult

    return RouteResult(
        duration_minutes=duration_minutes,
        distance_miles=distance_miles,
        data_age_minutes=0,
        confidence="verified",
    )


def _make_family_profile(max_total_driving_minutes: int = 120) -> Any:
    from nexus.state.schemas import FamilyProfile

    return FamilyProfile(max_total_driving_minutes=max_total_driving_minutes)


def _make_user_profile() -> Any:
    from nexus.state.schemas import UserProfile

    return UserProfile(
        name="Test",
        home_coordinates=(37.7749, -122.4194),
        max_driving_minutes=90,
    )


def _logistics_state(
    *,
    proposal: Any = None,
    route_duration: float = 45.0,
    max_driving: int = 120,
    start_hour: int = 9,
    duration_hours: float = 5.0,
) -> dict:
    """Build state with mock routing that returns a fixed route duration."""
    if proposal is None:
        proposal = _make_proposal(
            start_time=datetime(2026, 4, 19, start_hour, 0, tzinfo=timezone.utc),
            estimated_duration_hours=duration_hours,
        )

    mock_route = _make_route(route_duration)
    mock_routing = MagicMock()
    mock_routing.get_route = AsyncMock(return_value=mock_route)
    mock_routing.nearest_road_distance = AsyncMock(return_value=0.1)

    mock_registry = MagicMock()
    mock_registry.routing = mock_routing
    mock_registry.weather = MagicMock()

    user = _make_user_profile()
    family = _make_family_profile(max_total_driving_minutes=max_driving)

    state = _make_state(proposal=proposal)
    state["user_profile"] = user
    state["family_profile"] = family
    state["tool_registry"] = mock_registry
    state["meal_plan"] = None  # no restaurant route
    return state


# ─────────────────────────────────────────────────────────────────────────────
# Tests — driving time
# ─────────────────────────────────────────────────────────────────────────────


class TestLogisticsAgent:
    async def test_short_drive_approved(self):
        """45 min each way = 90 min total ≤ 120 min limit → APPROVED."""
        from nexus.agents.logistics import logistics_review

        state = _logistics_state(route_duration=45.0, max_driving=120)
        result = await logistics_review(state)

        verdicts = result["current_verdicts"]
        assert len(verdicts) == 1
        assert verdicts[0].agent_name == "logistics"
        assert verdicts[0].verdict == "APPROVED"
        assert verdicts[0].is_hard_constraint is True

    async def test_long_drive_rejected(self):
        """110 min each way = 220 min > 120 min limit → REJECTED."""
        from nexus.agents.logistics import logistics_review

        state = _logistics_state(route_duration=110.0, max_driving=120)
        result = await logistics_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "REJECTED"
        assert "220" in verdicts[0].rejection_reason or "120" in verdicts[0].rejection_reason

    async def test_exact_limit_boundary_approved(self):
        """60 min each way = 120 min == 120 min limit → APPROVED (boundary inclusive)."""
        from nexus.agents.logistics import logistics_review

        state = _logistics_state(route_duration=60.0, max_driving=120)
        result = await logistics_review(state)

        verdicts = result["current_verdicts"]
        # Total 120 == limit 120 — NOT over limit → APPROVED
        assert verdicts[0].verdict == "APPROVED"

    async def test_one_minute_over_limit_rejected(self):
        """61 min each way = 122 min > 120 min limit → REJECTED."""
        from nexus.agents.logistics import logistics_review

        state = _logistics_state(route_duration=61.0, max_driving=120)
        result = await logistics_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "REJECTED"

    # ─────────────────────────────────────────────────────────────────────────
    # Tests — timeline conflicts
    # ─────────────────────────────────────────────────────────────────────────

    async def test_departure_before_6am_rejected(self):
        """
        Start time 4:00, route 150 min → departure 01:30 (before 6:00) → REJECTED.
        Total driving 300 min also exceeds 120 min limit.
        """
        from nexus.agents.logistics import logistics_review

        # Start at 4am, 150-min drive → departure at 01:30 → before 06:00
        state = _logistics_state(start_hour=4, route_duration=150.0, max_driving=400)
        result = await logistics_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "REJECTED"
        # Should mention early departure
        reason = verdicts[0].rejection_reason.lower()
        assert "6" in reason or "am" in reason or "departure" in reason

    async def test_full_day_too_long_rejected(self):
        """
        Route 40 min each + 10h activity + 60 min meal = 800 min (13.3h) > 12h → REJECTED.
        Total driving 80 min is within 120 min limit.
        """
        from nexus.agents.logistics import logistics_review

        state = _logistics_state(
            start_hour=7,
            route_duration=40.0,
            duration_hours=10.0,  # 600 min activity
            max_driving=120,
        )
        result = await logistics_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "REJECTED"
        reason = verdicts[0].rejection_reason.lower()
        assert "12" in reason or "hour" in reason

    async def test_no_proposal_returns_approved(self):
        """Missing proposal → fallback APPROVED (no data to reject)."""
        from nexus.agents.logistics import logistics_review

        state = _logistics_state()
        state["primary_activity"] = None
        result = await logistics_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "APPROVED"

    async def test_route_data_returned(self):
        """route_data dict is always included in the return value."""
        from nexus.agents.logistics import logistics_review

        state = _logistics_state(route_duration=45.0)
        result = await logistics_review(state)

        assert "route_data" in result
        assert result["route_data"] is not None
        assert "home_to_activity" in result["route_data"]

    async def test_negotiation_log_populated(self):
        """negotiation_log must be non-empty for APPROVED case."""
        from nexus.agents.logistics import logistics_review

        state = _logistics_state(route_duration=45.0)
        result = await logistics_review(state)

        assert "negotiation_log" in result
        assert len(result["negotiation_log"]) > 0
        assert "logistics" in result["negotiation_log"][0].lower()
