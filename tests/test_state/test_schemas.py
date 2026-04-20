"""Tests for Pydantic state schemas — validation, rejection, and to_agent_verdict()."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TestAgentVerdict:
    def test_valid_approved(self):
        from nexus.state.schemas import AgentVerdict

        v = AgentVerdict(agent_name="meteorology", verdict="APPROVED", is_hard_constraint=True)
        assert v.verdict == "APPROVED"
        assert v.confidence == 1.0

    def test_valid_rejected(self):
        from nexus.state.schemas import AgentVerdict

        v = AgentVerdict(
            agent_name="safety",
            verdict="REJECTED",
            is_hard_constraint=True,
            rejection_reason="Remote location",
        )
        assert v.rejection_reason == "Remote location"

    def test_valid_needs_info(self):
        from nexus.state.schemas import AgentVerdict

        v = AgentVerdict(agent_name="nutritional", verdict="NEEDS_INFO", is_hard_constraint=False)
        assert v.verdict == "NEEDS_INFO"

    def test_invalid_verdict_value(self):
        from pydantic import ValidationError

        from nexus.state.schemas import AgentVerdict

        with pytest.raises(ValidationError):
            AgentVerdict(agent_name="x", verdict="MAYBE", is_hard_constraint=False)


class TestActivityProposal:
    def test_valid_proposal(self):
        from nexus.state.schemas import ActivityProposal

        p = ActivityProposal(
            activity_name="Mount Tam Hike",
            activity_type="hiking",
            location_coordinates=(37.9235, -122.5965),
            endpoint_coordinates=(37.9235, -122.5965),
            start_time=_now(),
            estimated_duration_hours=5.0,
        )
        assert p.activity_name == "Mount Tam Hike"
        assert p.require_cell_coverage is False  # default
        assert p.max_activity_hours == 8.0  # default

    def test_model_copy_mutation(self):
        """Mutation uses model_copy(update={}) — does not modify original."""
        from nexus.state.schemas import ActivityProposal

        original = ActivityProposal(
            activity_name="Hike",
            activity_type="hiking",
            location_coordinates=(37.0, -122.0),
            endpoint_coordinates=(37.0, -122.0),
            start_time=_now(),
            estimated_duration_hours=4.0,
        )
        mutated = original.model_copy(update={"require_cell_coverage": True})
        assert original.require_cell_coverage is False  # unchanged
        assert mutated.require_cell_coverage is True


class TestFamilyPlanVerdict:
    def test_to_agent_verdict(self):
        from nexus.state.schemas import FamilyPlanVerdict

        fpv = FamilyPlanVerdict(verdict="APPROVED", is_hard_constraint=True)
        av = fpv.to_agent_verdict()
        assert av.agent_name == "family_coordinator"
        assert av.verdict == "APPROVED"
        assert av.is_hard_constraint is True

    def test_to_agent_verdict_rejected(self):
        from nexus.state.schemas import FamilyPlanVerdict

        fpv = FamilyPlanVerdict(
            verdict="REJECTED",
            is_hard_constraint=True,
            rejection_reason="Teen requires cell service",
        )
        av = fpv.to_agent_verdict()
        assert av.verdict == "REJECTED"
        assert av.rejection_reason == "Teen requires cell service"


class TestNutritionalVerdict:
    def test_to_agent_verdict(self):
        from nexus.state.schemas import NutritionalVerdict

        nv = NutritionalVerdict(verdict="APPROVED", is_hard_constraint=True)
        av = nv.to_agent_verdict()
        assert av.agent_name == "nutritional"
        assert av.verdict == "APPROVED"


class TestBuildInitialState:
    def test_produces_valid_state(self, sample_config):
        from nexus.state.helpers import build_initial_state

        state = build_initial_state(
            user_intent="beach day with family",
            config=sample_config,
            request_id="test-001",
        )
        assert state["request_id"] == "test-001"
        assert state["user_intent"] == "beach day with family"
        assert state["iteration_count"] == 0
        assert state["max_iterations"] == 3
        assert state["current_phase"] == "drafting"
        assert state["current_verdicts"] == []
        assert state["proposal_history"] == []
        assert state["backup_activity"] is None

    def test_default_date_is_next_saturday(self, sample_config):
        from datetime import date

        from nexus.state.helpers import build_initial_state

        state = build_initial_state(user_intent="hike", config=sample_config)
        target = state["target_date"]
        assert isinstance(target, date)
        assert target.weekday() == 5  # Saturday
