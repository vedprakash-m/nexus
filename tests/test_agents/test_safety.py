"""
Deterministic tests for safety_review() agent — tasks 5.6 / 5.15.

All tests use mock activity + routing tools — no real API calls.
Exact verdict assertions (not LLM text).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_agents.test_meteorology import (
    _make_proposal,
    _make_state,
    _make_weather,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_family_profile(*, has_members: bool = True) -> object:
    from nexus.state.schemas import FamilyMember, FamilyProfile

    members = (
        [FamilyMember(name="Jamie", age=12)] if has_members else []
    )
    return FamilyProfile(members=members, max_total_driving_minutes=180)


def _make_route_result(duration_minutes: float = 30.0) -> object:
    from nexus.tools.models import RouteResult

    return RouteResult(
        duration_minutes=duration_minutes,
        distance_miles=10.0,
        data_age_minutes=0,
        confidence="verified",
    )


def _safety_state(
    *,
    has_hospitals: bool = True,
    has_family: bool = True,
    marginal_weather_precip: float = 5.0,  # < 30% threshold = not marginal
    road_proximity_miles: float = 0.1,      # < 0.5 = has coverage
    start_hour: int = 9,
    duration_hours: float = 5.0,
    route_duration: float = 60.0,
    sunset_hour: int = 20,  # 8pm = plenty of buffer
) -> dict:
    """Build minimal state for safety_review() tests."""
    proposal = _make_proposal(
        start_time=datetime(2026, 4, 19, start_hour, 0, tzinfo=timezone.utc),
        estimated_duration_hours=duration_hours,
    )

    sunset_time = datetime(2026, 4, 19, sunset_hour, 0, tzinfo=timezone.utc)
    weather = _make_weather(
        precipitation_probability=marginal_weather_precip,
    )
    # Override daylight window with parameterised sunset
    from nexus.tools.models import DaylightWindow

    weather = weather.model_copy(
        update={
            "daylight": DaylightWindow(
                sunrise=datetime(2026, 4, 19, 6, 30, tzinfo=timezone.utc),
                sunset=sunset_time,
                data_age_minutes=0,
                confidence="verified",
            )
        }
    )

    hospital_results = (
        [MagicMock(name="SF General")] if has_hospitals else []
    )

    mock_activity = MagicMock()
    mock_activity.search_activities = AsyncMock(return_value=hospital_results)

    mock_routing = MagicMock()
    mock_routing.get_route = AsyncMock(return_value=_make_route_result(route_duration))
    mock_routing.nearest_road_distance = AsyncMock(return_value=road_proximity_miles)

    mock_registry = MagicMock()
    mock_registry.activity = mock_activity
    mock_registry.routing = mock_routing

    family = _make_family_profile(has_members=has_family)

    state = _make_state(proposal=proposal)
    state["weather_data"] = weather
    state["family_profile"] = family if has_family else None
    state["tool_registry"] = mock_registry
    state["route_data"] = {
        "restaurant_to_home": _make_route_result(route_duration),
    }
    return state


# ─────────────────────────────────────────────────────────────────────────────
# Tests — hospital proximity + family + marginal weather
# ─────────────────────────────────────────────────────────────────────────────


class TestSafetyAgent:
    async def test_all_clear_approved(self):
        """Hospital nearby, family, good weather, good coverage → APPROVED."""
        from nexus.agents.safety import safety_review

        state = _safety_state(
            has_hospitals=True,
            has_family=True,
            marginal_weather_precip=5.0,
            road_proximity_miles=0.1,
        )
        result = await safety_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].agent_name == "safety"
        assert verdicts[0].verdict == "APPROVED"
        assert verdicts[0].is_hard_constraint is True

    async def test_remote_family_marginal_weather_rejected(self):
        """
        No hospital within 30 mi + family + >30% precip → REJECTED.
        All three conditions must be present.
        """
        from nexus.agents.safety import safety_review

        state = _safety_state(
            has_hospitals=False,   # remote
            has_family=True,       # family present
            marginal_weather_precip=35.0,  # > 30% threshold
        )
        result = await safety_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "REJECTED"
        reason = verdicts[0].rejection_reason.lower()
        assert "remote" in reason or "hospital" in reason

    async def test_remote_no_family_not_rejected(self):
        """Remote + NO family: solo adventure is allowed (no family safety constraint)."""
        from nexus.agents.safety import safety_review

        state = _safety_state(
            has_hospitals=False,
            has_family=False,
            marginal_weather_precip=35.0,
        )
        result = await safety_review(state)

        # Remote without family does not trigger the safety rejection
        verdicts = result["current_verdicts"]
        # May still be REJECTED due to coverage — but NOT due to hospital proximity alone
        # The hospital rejection requires: remote AND has_family AND marginal_weather
        # Without family, that condition is False
        reason = (verdicts[0].rejection_reason or "").lower()
        assert "remote" not in reason and "hospital" not in reason

    async def test_remote_family_good_weather_approved(self):
        """Remote + family + precip < 30% → hospital condition not met → APPROVED."""
        from nexus.agents.safety import safety_review

        state = _safety_state(
            has_hospitals=False,
            has_family=True,
            marginal_weather_precip=20.0,  # < 30% threshold → not marginal
        )
        result = await safety_review(state)

        # marginal_weather = False → combined condition is False → no hospital rejection
        verdicts = result["current_verdicts"]
        reason = (verdicts[0].rejection_reason or "").lower()
        assert "hospital" not in reason and "remote" not in reason

    # ─────────────────────────────────────────────────────────────────────────
    # Tests — post-sunset return
    # ─────────────────────────────────────────────────────────────────────────

    async def test_post_sunset_return_rejected(self):
        """
        Activity ends + drive home after sunset buffer → REJECTED.
        Start 9am + 10h activity + 60 min drive = return 20:00.
        Sunset at 19:00 → buffer at 18:30 → return after buffer → REJECTED.
        """
        from nexus.agents.safety import safety_review

        # 9am + 10h activity + 60 min drive = 20:00 return
        # Sunset 19:00 - 30 min buffer = 18:30 deadline
        state = _safety_state(
            has_hospitals=True,
            has_family=False,
            marginal_weather_precip=5.0,
            road_proximity_miles=0.1,
            start_hour=9,
            duration_hours=10.0,
            route_duration=60.0,
            sunset_hour=19,  # Sunset at 19:00
        )
        result = await safety_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "REJECTED"
        reason = verdicts[0].rejection_reason.lower()
        assert "sunset" in reason or "return" in reason

    async def test_well_before_sunset_approved(self):
        """Return home well before sunset → APPROVED."""
        from nexus.agents.safety import safety_review

        # 8am + 4h + 30 min = 12:30 return — sunset at 20:00 → fine
        state = _safety_state(
            has_hospitals=True,
            has_family=False,
            start_hour=8,
            duration_hours=4.0,
            route_duration=30.0,
            sunset_hour=20,
        )
        result = await safety_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "APPROVED"

    # ─────────────────────────────────────────────────────────────────────────
    # Tests — cell coverage
    # ─────────────────────────────────────────────────────────────────────────

    async def test_poor_cell_coverage_rejected(self):
        """
        Road > 0.5 mi away → poor coverage estimate → REJECTED.
        """
        from nexus.agents.safety import safety_review

        state = _safety_state(
            has_hospitals=True,
            has_family=False,
            marginal_weather_precip=5.0,
            road_proximity_miles=2.0,  # > 0.5 mi threshold → poor coverage
        )
        result = await safety_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "REJECTED"
        reason = verdicts[0].rejection_reason.lower()
        assert "coverage" in reason or "cell" in reason

    async def test_no_proposal_returns_approved(self):
        """Missing proposal → fallback APPROVED."""
        from nexus.agents.safety import safety_review

        state = _safety_state()
        state["primary_activity"] = None
        result = await safety_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "APPROVED"

    async def test_negotiation_log_populated(self):
        """negotiation_log must be non-empty."""
        from nexus.agents.safety import safety_review

        state = _safety_state()
        result = await safety_review(state)

        assert "negotiation_log" in result
        assert len(result["negotiation_log"]) > 0
        assert "safety" in result["negotiation_log"][0].lower()
