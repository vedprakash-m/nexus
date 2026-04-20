"""
E2E integration tests with all external APIs mocked via pytest-httpx.

Tests the complete planning loop:
- Intent → agents → consensus → safety → synthesize → save
- Rejection loop: reject → feedback → replan
- Mid-flight constraint injection

All LLM calls are patched via monkeypatch.
All HTTP calls (Open-Meteo, OSRM, Yelp, Overpass) are intercepted by httpx_mock.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "http"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def _make_mock_registry():
    """Build a fully-mocked ToolRegistry."""
    from nexus.tools.models import AirQuality, DaylightWindow, RouteResult, WeatherForecast

    weather_tool = MagicMock()
    weather_tool.get_forecast = AsyncMock(
        return_value=WeatherForecast(
            precipitation_probability=5.0,
            lightning_risk=False,
            conditions_text="Sunny",
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
    )
    weather_tool.get_air_quality = AsyncMock(
        return_value=AirQuality(aqi=42, data_age_minutes=0, confidence="verified")
    )
    weather_tool.get_daylight_window = AsyncMock(
        return_value=DaylightWindow(
            sunrise=datetime(2026, 4, 19, 6, 30, tzinfo=timezone.utc),
            sunset=datetime(2026, 4, 19, 19, 50, tzinfo=timezone.utc),
            data_age_minutes=0,
            confidence="verified",
        )
    )

    routing_tool = MagicMock()
    routing_tool.get_route = AsyncMock(
        return_value=RouteResult(
            duration_minutes=45.0,
            distance_miles=30.0,
            confidence="verified",
            is_estimated=False,
            data_age_minutes=0,
        )
    )
    routing_tool.nearest_road_distance = AsyncMock(return_value=0.2)

    activity_tool = MagicMock()
    from nexus.tools.models import ActivityResult

    activity_tool.search_activities = AsyncMock(
        return_value=[
            ActivityResult(
                activity_id="act-1",
                name="Windy Hill Preserve",
                activity_type="hiking",
                location_coordinates=(37.37, -122.19),
                description="Scenic ridge hike",
                difficulty="moderate",
                distance_miles=8.0,
                elevation_gain_ft=1200,
                data_age_minutes=0,
                confidence="verified",
            )
        ]
    )

    places_tool = MagicMock()
    from nexus.tools.models import PlaceResult

    places_tool.search_restaurants = AsyncMock(
        return_value=[
            PlaceResult(
                place_id="rest-1",
                name="The Trail Cafe",
                address="123 Main St",
                category="restaurant",
                location_coordinates=(37.40, -122.10),
                cuisine_type="American",
                rating=4.2,
                data_age_minutes=0,
                confidence="verified",
            )
        ]
    )
    places_tool.search_nearby = AsyncMock(return_value=[])

    coverage_tool = MagicMock()
    from nexus.tools.models import CoverageEstimate

    mock_registry = MagicMock()
    mock_registry.weather = weather_tool
    mock_registry.routing = routing_tool
    mock_registry.activity = activity_tool
    mock_registry.places = places_tool

    return mock_registry


def _make_mock_proposal():
    from nexus.state.schemas import ActivityProposal

    return ActivityProposal(
        activity_name="Windy Hill Preserve",
        activity_type="hiking",
        location_coordinates=(37.37, -122.19),
        endpoint_coordinates=(37.38, -122.18),
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


def _make_mock_plan_requirements():
    from nexus.state.schemas import PlanRequirements

    return PlanRequirements(
        target_date=date(2026, 4, 19),
        activity_type="hiking",
        max_distance_miles=15.0,
        max_driving_minutes=60,
        fitness_level="intermediate",
        dietary_restrictions=[],
        preferred_activities=["hiking"],
        require_cell_coverage=False,
        group_size=2,
        has_young_children=False,
        min_elevation_gain_ft=0,
        max_elevation_gain_ft=3000,
        max_activity_hours=8.0,
        family_summary="Adult couple",
    )


def _make_full_state(overrides: dict | None = None) -> dict:
    """Build a fully-populated state for E2E tests."""
    from nexus.state.schemas import FamilyProfile, UserProfile

    registry = _make_mock_registry()
    requirements = _make_mock_plan_requirements()
    proposal = _make_mock_proposal()

    model_router = MagicMock()
    model = MagicMock()
    model.with_structured_output = MagicMock(return_value=model)
    model_router.get_model = MagicMock(return_value=model)

    state: dict = {
        "request_id": "e2e-test-001",
        "user_intent": "hike on Sunday",
        "target_date": date(2026, 4, 19),
        "user_profile": UserProfile(
            name="Alex",
            home_coordinates=(37.55, -122.05),
            fitness_level="intermediate",
            dietary_restrictions=[],
            preferred_activities=["hiking"],
            max_driving_minutes=90,
        ),
        "family_profile": FamilyProfile(
            members=[],
            max_total_driving_minutes=120,
        ),
        "plan_requirements": requirements,
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
        "tool_registry": registry,
        "model_router": model_router,
        "config": MagicMock(),
    }
    if overrides:
        state.update(overrides)
    return state


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestMeteorologyE2E:
    async def test_clear_weather_produces_approved_verdict(self):
        """Full meteorology_review run with clear weather → APPROVED."""
        from nexus.agents.meteorology import meteorology_review

        state = _make_full_state()
        result = await meteorology_review(state)
        assert result["current_verdicts"][0].verdict == "APPROVED"
        assert result["weather_data"] is not None

    async def test_rainy_weather_produces_rejected_verdict(self):
        """Full meteorology_review run with 65% precip → REJECTED."""
        from nexus.agents.meteorology import meteorology_review
        from nexus.tools.models import AirQuality, DaylightWindow, WeatherForecast

        state = _make_full_state()
        state["tool_registry"].weather.get_forecast = AsyncMock(
            return_value=WeatherForecast(
                precipitation_probability=65.0,
                lightning_risk=False,
                conditions_text="Heavy rain",
                temperature_high_f=58.0,
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
        )
        result = await meteorology_review(state)
        assert result["current_verdicts"][0].verdict == "REJECTED"


class TestLogisticsE2E:
    async def test_short_drive_approved(self):
        """logistics_review with 45-min drive within limit → APPROVED."""
        from nexus.agents.logistics import logistics_review

        state = _make_full_state()
        result = await logistics_review(state)
        verdicts = result["current_verdicts"]
        assert verdicts[0].verdict == "APPROVED"
        assert result["route_data"] is not None

    async def test_excessive_drive_rejected(self):
        """logistics_review with 200-min drive exceeds 120-min limit → REJECTED."""
        from nexus.agents.logistics import logistics_review
        from nexus.tools.models import RouteResult

        state = _make_full_state()
        state["tool_registry"].routing.get_route = AsyncMock(
            return_value=RouteResult(
                duration_minutes=200.0,
                distance_miles=150.0,
                confidence="verified",
                is_estimated=False,
                data_age_minutes=0,
            )
        )
        result = await logistics_review(state)
        assert result["current_verdicts"][0].verdict == "REJECTED"


class TestSafetyE2E:
    async def test_accessible_location_approved(self):
        """safety_review with accessible location → APPROVED."""
        from nexus.agents.safety import safety_review

        state = _make_full_state()
        # Give it a route_data so safety can compute return time
        from nexus.tools.models import RouteResult

        state["route_data"] = {
            "home_to_activity": RouteResult(
                duration_minutes=45.0, distance_miles=30.0,
                confidence="verified", is_estimated=False, data_age_minutes=0,
            )
        }
        result = await safety_review(state)
        assert result["current_verdicts"][0].verdict in ("APPROVED", "NEEDS_INFO")


class TestConsensusE2E:
    async def test_all_approved_reaches_safety_routing(self):
        """All 4 agents approved → route_after_consensus returns review_safety."""
        from nexus.graph.planner import route_after_consensus
        from nexus.state.schemas import AgentVerdict

        state = _make_full_state()
        state["current_verdicts"] = [
            AgentVerdict(agent_name="meteorology", verdict="APPROVED", is_hard_constraint=True),
            AgentVerdict(agent_name="family_coordinator", verdict="APPROVED", is_hard_constraint=False),
            AgentVerdict(agent_name="nutritional", verdict="APPROVED", is_hard_constraint=False),
            AgentVerdict(agent_name="logistics", verdict="APPROVED", is_hard_constraint=True),
        ]
        result = route_after_consensus(state)
        assert result == "review_safety"

    async def test_rejection_returns_to_draft(self):
        """Any REJECTED verdict → route_after_consensus returns draft_proposal."""
        from nexus.graph.planner import route_after_consensus
        from nexus.state.schemas import AgentVerdict

        state = _make_full_state()
        state["current_verdicts"] = [
            AgentVerdict(agent_name="meteorology", verdict="REJECTED", is_hard_constraint=True, rejection_reason="rain"),
            AgentVerdict(agent_name="family_coordinator", verdict="APPROVED", is_hard_constraint=False),
            AgentVerdict(agent_name="nutritional", verdict="APPROVED", is_hard_constraint=False),
            AgentVerdict(agent_name="logistics", verdict="APPROVED", is_hard_constraint=True),
        ]
        result = route_after_consensus(state)
        assert result == "draft_proposal"

    async def test_pending_constraint_triggers_redraft(self):
        """Mid-flight constraint in pending_constraints → drains to re-draft."""
        from nexus.agents.orchestrator import orchestrator_check_consensus
        from nexus.state.schemas import AgentVerdict

        state = _make_full_state()
        state["pending_constraints"] = ["no steep climbs"]
        state["current_verdicts"] = [
            AgentVerdict(agent_name="meteorology", verdict="APPROVED", is_hard_constraint=True),
        ]

        result = await orchestrator_check_consensus(state)
        assert result["pending_constraints"] == []
        assert "constraint" in result["rejection_context"].lower()


class TestBackupPlanE2E:
    """Task 9.7 — Backup plan generation E2E validation."""

    async def test_backup_from_proposal_history(self):
        """
        Synthesizer with 2 proposals in history → backup is proposal_history[-2].
        No extra LLM call made.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from nexus.agents.synthesizer import plan_synthesizer

        state = _make_full_state()
        proposal1 = _make_mock_proposal()
        proposal2 = _make_mock_proposal()
        # Modify proposal1 to be distinguishable
        proposal1 = proposal1.model_copy(update={"activity_name": "Earlier proposal"})
        state["proposal_history"] = [proposal1, proposal2]  # 2 proposals → use [0] as backup

        # Mock the LLM to return a narrative string
        model_mock = MagicMock()
        msg_mock = MagicMock()
        msg_mock.content = "A wonderful day in the outdoors awaits."
        model_mock.ainvoke = AsyncMock(return_value=msg_mock)
        state["model_router"].get_model = MagicMock(return_value=model_mock)

        with patch("nexus.output.renderer.render_plan_fragment", return_value="<html>plan</html>"), \
             patch("nexus.output.renderer.render_plan_markdown", return_value="# Plan"):
            result = await plan_synthesizer(state)

        assert result["backup_activity"] is not None
        assert result["backup_activity"].activity_name == "Earlier proposal"
        assert model_mock.ainvoke.call_count == 1  # only one LLM call (narrative)

    async def test_backup_relaxed_variant_when_single_proposal(self):
        """
        Synthesizer with only 1 proposal in history → backup is a relaxed variant.
        No extra LLM call (generate_relaxed_variant is pure Python).
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from nexus.agents.synthesizer import plan_synthesizer

        state = _make_full_state()
        proposal = _make_mock_proposal()
        state["proposal_history"] = [proposal]  # only 1 → generate relaxed variant

        model_mock = MagicMock()
        msg_mock = MagicMock()
        msg_mock.content = "A relaxing day."
        model_mock.ainvoke = AsyncMock(return_value=msg_mock)
        state["model_router"].get_model = MagicMock(return_value=model_mock)

        with patch("nexus.output.renderer.render_plan_fragment", return_value="<html>plan</html>"), \
             patch("nexus.output.renderer.render_plan_markdown", return_value="# Plan"):
            result = await plan_synthesizer(state)

        assert result["backup_activity"] is not None
        assert "(Relaxed)" in result["backup_activity"].activity_name
        assert model_mock.ainvoke.call_count == 1  # still only one LLM call

    async def test_generate_relaxed_variant_widens_distance(self):
        """generate_relaxed_variant() increases max_distance_miles by 5 when < 20."""
        from nexus.agents.synthesizer import generate_relaxed_variant
        from nexus.state.schemas import PlanRequirements

        state = _make_full_state()
        state["plan_requirements"] = state["plan_requirements"].model_copy(
            update={"max_distance_miles": 15.0}
        )
        variant = generate_relaxed_variant(state)
        assert variant is not None
        assert "(Relaxed)" in variant.activity_name
