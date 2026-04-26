"""
Tests for consensus detection helpers:
- all_agents_approved()
- has_critical_safety_rejection()
"""

from __future__ import annotations

from datetime import date

from nexus.state.helpers import all_agents_approved, has_critical_safety_rejection
from nexus.state.schemas import AgentFailureType, AgentVerdict


def _base_state() -> dict:
    """Build a minimal WeekendPlanState dict for consensus tests."""
    return {
        "request_id": "test-id",
        "user_intent": "hike",
        "target_date": date.today(),
        "user_profile": None,
        "family_profile": None,
        "plan_requirements": None,
        "primary_activity": None,
        "family_activities": [],
        "meal_plan": None,
        "proposal_history": [],
        "current_verdicts": [],
        "weather_data": None,
        "route_data": None,
        "safety_data": None,
        "iteration_count": 0,
        "max_iterations": 3,
        "current_phase": "drafting",
        "rejection_context": None,
        "pending_constraints": [],
        "negotiation_log": [],
        "human_feedback": None,
        "output_html": None,
        "output_markdown": None,
        "backup_activity": None,
        "human_rejection_count": 0,
        "output_confidence_labels": None,
    }


class TestAllAgentsApproved:
    def test_all_four_approved(self):
        state = _base_state()
        state["current_verdicts"] = [
            AgentVerdict(
                agent_name="meteorology",
                verdict="APPROVED",
                is_hard_constraint=False,
                confidence=1.0,
            ),
            AgentVerdict(
                agent_name="family_coordinator",
                verdict="APPROVED",
                is_hard_constraint=False,
                confidence=1.0,
            ),
            AgentVerdict(
                agent_name="nutritional",
                verdict="APPROVED",
                is_hard_constraint=False,
                confidence=1.0,
            ),
            AgentVerdict(
                agent_name="logistics", verdict="APPROVED", is_hard_constraint=False, confidence=1.0
            ),
        ]
        assert all_agents_approved(state) is True

    def test_needs_info_counts_as_approved(self):
        state = _base_state()
        state["current_verdicts"] = [
            AgentVerdict(
                agent_name="meteorology",
                verdict="APPROVED",
                is_hard_constraint=False,
                confidence=1.0,
            ),
            AgentVerdict(
                agent_name="family_coordinator",
                verdict="NEEDS_INFO",
                is_hard_constraint=False,
                confidence=0.7,
            ),
            AgentVerdict(
                agent_name="nutritional",
                verdict="APPROVED",
                is_hard_constraint=False,
                confidence=1.0,
            ),
            AgentVerdict(
                agent_name="logistics", verdict="APPROVED", is_hard_constraint=False, confidence=1.0
            ),
        ]
        assert all_agents_approved(state) is True

    def test_one_rejected_returns_false(self):
        state = _base_state()
        state["current_verdicts"] = [
            AgentVerdict(
                agent_name="meteorology",
                verdict="REJECTED",
                is_hard_constraint=True,
                confidence=1.0,
            ),
            AgentVerdict(
                agent_name="family_coordinator",
                verdict="APPROVED",
                is_hard_constraint=False,
                confidence=1.0,
            ),
            AgentVerdict(
                agent_name="nutritional",
                verdict="APPROVED",
                is_hard_constraint=False,
                confidence=1.0,
            ),
            AgentVerdict(
                agent_name="logistics", verdict="APPROVED", is_hard_constraint=False, confidence=1.0
            ),
        ]
        assert all_agents_approved(state) is False

    def test_missing_agent_returns_false(self):
        """Only 3 of 4 required agents have verdicts."""
        state = _base_state()
        state["current_verdicts"] = [
            AgentVerdict(
                agent_name="meteorology",
                verdict="APPROVED",
                is_hard_constraint=False,
                confidence=1.0,
            ),
            AgentVerdict(
                agent_name="family_coordinator",
                verdict="APPROVED",
                is_hard_constraint=False,
                confidence=1.0,
            ),
            AgentVerdict(
                agent_name="nutritional",
                verdict="APPROVED",
                is_hard_constraint=False,
                confidence=1.0,
            ),
            # logistics missing
        ]
        assert all_agents_approved(state) is False

    def test_empty_verdicts_returns_false(self):
        state = _base_state()
        state["current_verdicts"] = []
        assert all_agents_approved(state) is False


class TestHasCriticalSafetyRejection:
    def test_hard_constraint_data_unavailable_is_critical(self):
        state = _base_state()
        state["current_verdicts"] = [
            AgentVerdict(
                agent_name="safety",
                verdict="REJECTED",
                is_hard_constraint=True,
                confidence=1.0,
                failure_type=AgentFailureType.DATA_UNAVAILABLE,
            )
        ]
        assert has_critical_safety_rejection(state) is True

    def test_soft_rejection_is_not_critical(self):
        state = _base_state()
        state["current_verdicts"] = [
            AgentVerdict(
                agent_name="meteorology",
                verdict="REJECTED",
                is_hard_constraint=False,
                confidence=1.0,
            )
        ]
        assert has_critical_safety_rejection(state) is False

    def test_no_verdicts_is_not_critical(self):
        state = _base_state()
        state["current_verdicts"] = []
        assert has_critical_safety_rejection(state) is False

    def test_hard_block_without_data_unavailable_is_not_critical(self):
        """HARD_CONSTRAINT_BLOCK alone (without DATA_UNAVAILABLE) is NOT a critical failure.
        Critical = specifically DATA_UNAVAILABLE where no fallback exists."""
        state = _base_state()
        state["current_verdicts"] = [
            AgentVerdict(
                agent_name="weather",
                verdict="REJECTED",
                is_hard_constraint=True,
                confidence=1.0,
                failure_type=AgentFailureType.HARD_CONSTRAINT_BLOCK,
            )
        ]
        # HARD_CONSTRAINT_BLOCK is a normal hard rejection — not a system failure
        assert has_critical_safety_rejection(state) is False
