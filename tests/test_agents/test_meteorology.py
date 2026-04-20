"""
Tests for deterministic agent threshold behavior.

All tests use mock tool registry and weather fixtures — no real API calls.
Exact verdict assertions (not LLM text).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_proposal(**kwargs) -> Any:
    from nexus.state.schemas import ActivityProposal

    defaults = dict(
        activity_name="Test Hike",
        activity_type="hiking",
        location_coordinates=(37.7749, -122.4194),
        endpoint_coordinates=(37.7800, -122.4200),
        route_waypoints=[],
        start_time=datetime(2026, 4, 19, 9, 0, tzinfo=timezone.utc),
        estimated_duration_hours=5.0,
        estimated_return_after_sunset=False,
        has_exposed_sections=False,
        difficulty="moderate",
        max_distance_miles=10.0,
        min_elevation_ft=0,
        search_radius_miles=30.0,
        require_cell_coverage=False,
        max_activity_hours=8.0,
    )
    defaults.update(kwargs)
    return ActivityProposal(**defaults)


def _make_weather(**kwargs) -> Any:
    from nexus.tools.models import AirQuality, DaylightWindow, WeatherForecast

    defaults = dict(
        precipitation_probability=5.0,
        lightning_risk=False,
        conditions_text="Partly cloudy",
        temperature_high_f=72.0,
        aqi=AirQuality(aqi=42, data_age_minutes=0, confidence="verified"),
        daylight=DaylightWindow(
            sunrise=datetime(2026, 4, 19, 6, 30, tzinfo=timezone.utc),
            sunset=datetime(2026, 4, 19, 19, 50, tzinfo=timezone.utc),
            data_age_minutes=0,
            confidence="verified",
        ),
        data_age_minutes=0,
        confidence="verified",
    )
    defaults.update(kwargs)
    return WeatherForecast(**defaults)


def _make_mock_weather_tool(forecast=None, aqi=None, daylight=None):
    """Build a mock weather tool that returns preset values."""
    from nexus.tools.models import AirQuality, DaylightWindow

    weather = forecast or _make_weather()
    mock_tool = MagicMock()
    mock_tool.get_forecast = AsyncMock(return_value=weather)
    mock_tool.get_air_quality = AsyncMock(
        return_value=aqi or AirQuality(aqi=42, data_age_minutes=0, confidence="verified")
    )
    mock_tool.get_daylight_window = AsyncMock(
        return_value=daylight
        or DaylightWindow(
            sunrise=datetime(2026, 4, 19, 6, 30, tzinfo=timezone.utc),
            sunset=datetime(2026, 4, 19, 19, 50, tzinfo=timezone.utc),
            data_age_minutes=0,
            confidence="verified",
        )
    )
    return mock_tool


def _make_state(proposal=None, weather_tool=None, **overrides) -> dict:
    """Build minimal state for agent tests."""
    from nexus.tools.models import AirQuality, DaylightWindow, WeatherForecast

    mock_registry = MagicMock()
    mock_registry.weather = weather_tool or _make_mock_weather_tool()
    mock_registry.routing = MagicMock()
    mock_registry.routing.nearest_road_distance = AsyncMock(return_value=0.1)

    state: dict = {
        "request_id": "test-req",
        "user_intent": "hike",
        "target_date": date(2026, 4, 19),
        "user_profile": None,
        "family_profile": None,
        "plan_requirements": None,
        "primary_activity": proposal,
        "family_activities": [],
        "meal_plan": None,
        "proposal_history": [],
        "current_verdicts": [],
        "weather_data": None,
        "route_data": None,
        "safety_data": None,
        "iteration_count": 0,
        "max_iterations": 3,
        "current_phase": "reviewing",
        "rejection_context": None,
        "pending_constraints": [],
        "negotiation_log": [],
        "human_feedback": None,
        "output_html": None,
        "output_markdown": None,
        "backup_activity": None,
        "human_rejection_count": 0,
        "output_confidence_labels": None,
        "tool_registry": mock_registry,
        "model_router": MagicMock(),
        "config": MagicMock(),
    }
    state.update(overrides)
    return state


class TestMeteorologyAgent:
    async def test_clear_weather_approved(self):
        from nexus.agents.meteorology import meteorology_review

        proposal = _make_proposal()
        state = _make_state(proposal=proposal)
        result = await meteorology_review(state)

        verdicts = result["current_verdicts"]
        assert len(verdicts) == 1
        assert verdicts[0].verdict == "APPROVED"
        assert verdicts[0].agent_name == "meteorology"

    async def test_high_precip_rejected(self):
        from nexus.agents.meteorology import meteorology_review
        from nexus.tools.models import AirQuality, DaylightWindow

        # 65% precipitation → above 40% threshold
        weather_tool = _make_mock_weather_tool()
        weather_tool.get_forecast = AsyncMock(
            return_value=_make_weather(precipitation_probability=65.0)
        )
        proposal = _make_proposal()
        state = _make_state(proposal=proposal, weather_tool=weather_tool)

        result = await meteorology_review(state)

        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "REJECTED"
        assert verdicts[0].is_hard_constraint is True
        assert "65" in verdicts[0].rejection_reason

    async def test_high_aqi_rejected(self):
        from nexus.agents.meteorology import meteorology_review
        from nexus.tools.models import AirQuality

        weather_tool = _make_mock_weather_tool(
            aqi=AirQuality(aqi=115, data_age_minutes=0, confidence="verified")
        )
        proposal = _make_proposal()
        state = _make_state(proposal=proposal, weather_tool=weather_tool)

        result = await meteorology_review(state)
        assert result["current_verdicts"][0].verdict == "REJECTED"
        assert "115" in result["current_verdicts"][0].rejection_reason

    async def test_lightning_with_exposed_sections_rejected(self):
        from nexus.agents.meteorology import meteorology_review

        weather_tool = _make_mock_weather_tool(
            forecast=_make_weather(lightning_risk=True)
        )
        proposal = _make_proposal(has_exposed_sections=True)
        state = _make_state(proposal=proposal, weather_tool=weather_tool)

        result = await meteorology_review(state)
        assert result["current_verdicts"][0].verdict == "REJECTED"
        assert "lightning" in result["current_verdicts"][0].rejection_reason.lower()

    async def test_lightning_without_exposed_sections_approved(self):
        """Lightning risk doesn't reject if route has no exposed sections."""
        from nexus.agents.meteorology import meteorology_review

        weather_tool = _make_mock_weather_tool(
            forecast=_make_weather(lightning_risk=True)
        )
        proposal = _make_proposal(has_exposed_sections=False)
        state = _make_state(proposal=proposal, weather_tool=weather_tool)

        result = await meteorology_review(state)
        assert result["current_verdicts"][0].verdict == "APPROVED"

    async def test_activity_after_sunset_rejected(self):
        """Activity ending 10 min before sunset (< 30 min buffer) → rejected."""
        from nexus.agents.meteorology import meteorology_review
        from nexus.tools.models import DaylightWindow

        sunset = datetime(2026, 4, 19, 19, 50, tzinfo=timezone.utc)
        daylight = DaylightWindow(
            sunrise=datetime(2026, 4, 19, 6, 30, tzinfo=timezone.utc),
            sunset=sunset,
            data_age_minutes=0,
            confidence="verified",
        )
        # Activity starts at 09:00, lasts 11 hours → ends 20:00 > sunset 19:50
        proposal = _make_proposal(
            start_time=datetime(2026, 4, 19, 9, 0, tzinfo=timezone.utc),
            estimated_duration_hours=11.0,
        )
        weather_tool = _make_mock_weather_tool(daylight=daylight)
        state = _make_state(proposal=proposal, weather_tool=weather_tool)

        result = await meteorology_review(state)
        assert result["current_verdicts"][0].verdict == "REJECTED"

    async def test_no_proposal_approved(self):
        """No proposal → default APPROVED."""
        from nexus.agents.meteorology import meteorology_review

        state = _make_state(proposal=None)
        result = await meteorology_review(state)
        assert result["current_verdicts"][0].verdict == "APPROVED"


class TestErrorBoundary:
    async def test_hard_constraint_exception_returns_rejected(self):
        from nexus.agents.error_boundary import agent_error_boundary

        @agent_error_boundary("test_agent", is_hard_constraint=True)
        async def bad_agent(state):
            raise ValueError("something went wrong")

        result = await bad_agent({})
        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "REJECTED"
        assert verdicts[0].failure_type is not None

    async def test_soft_constraint_exception_returns_needs_info(self):
        from nexus.agents.error_boundary import agent_error_boundary

        @agent_error_boundary("soft_agent", is_hard_constraint=False)
        async def soft_bad(state):
            raise RuntimeError("data unavailable")

        result = await soft_bad({})
        assert result["current_verdicts"][0].verdict == "NEEDS_INFO"

    async def test_hard_constraint_data_unavailable_propagates(self):
        """HardConstraintDataUnavailable must re-raise, not be swallowed."""
        from nexus.agents.error_boundary import agent_error_boundary
        from nexus.resilience import HardConstraintDataUnavailable

        @agent_error_boundary("critical", is_hard_constraint=True)
        async def critical_agent(state):
            raise HardConstraintDataUnavailable("weather data unavailable")

        with pytest.raises(HardConstraintDataUnavailable):
            await critical_agent({})

    async def test_timeout_sets_correct_failure_type(self):
        import asyncio

        from nexus.agents.error_boundary import agent_error_boundary
        from nexus.state.schemas import AgentFailureType

        @agent_error_boundary("slow_agent", is_hard_constraint=True)
        async def slow_agent(state):
            raise asyncio.TimeoutError()

        result = await slow_agent({})
        assert result["current_verdicts"][0].failure_type == AgentFailureType.TIMEOUT
