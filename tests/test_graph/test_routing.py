"""
Tests for routing functions — all conditional branches of
route_after_consensus() and route_after_safety().
"""

from __future__ import annotations

from datetime import date


from nexus.graph.planner import route_after_consensus, route_after_safety
from nexus.state.schemas import AgentVerdict
from langgraph.graph import END


def _base_state() -> dict:
    """Build a minimal WeekendPlanState dict for routing tests."""
    today = date.today()
    return {
        "request_id": "test-id",
        "user_intent": "hike",
        "target_date": today,
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


def _approved_verdict(agent: str) -> AgentVerdict:
    return AgentVerdict(
        agent_name=agent,
        verdict="APPROVED",
        is_hard_constraint=False,
        confidence=1.0,
    )


def _rejected_verdict(agent: str, is_hard: bool = False) -> AgentVerdict:
    return AgentVerdict(
        agent_name=agent,
        verdict="REJECTED",
        is_hard_constraint=is_hard,
        confidence=1.0,
        rejection_reason="test rejection",
    )


def _needs_info_verdict(agent: str) -> AgentVerdict:
    return AgentVerdict(
        agent_name=agent,
        verdict="NEEDS_INFO",
        is_hard_constraint=False,
        confidence=0.7,
    )


class TestRouteAfterConsensus:
    def test_all_approved_goes_to_safety(self):
        state = _base_state()
        state["current_verdicts"] = [
            _approved_verdict("meteorology"),
            _approved_verdict("family_coordinator"),
            _approved_verdict("nutritional"),
            _approved_verdict("logistics"),
        ]
        assert route_after_consensus(state) == "review_safety"

    def test_needs_info_passes_through_as_approved(self):
        """NEEDS_INFO alone does not block consensus (REC-5)."""
        state = _base_state()
        state["current_verdicts"] = [
            _approved_verdict("meteorology"),
            _needs_info_verdict("family_coordinator"),
            _approved_verdict("nutritional"),
            _approved_verdict("logistics"),
        ]
        assert route_after_consensus(state) == "review_safety"

    def test_one_rejection_routes_to_redraft(self):
        state = _base_state()
        state["current_verdicts"] = [
            _rejected_verdict("meteorology"),
            _approved_verdict("family_coordinator"),
            _approved_verdict("nutritional"),
            _approved_verdict("logistics"),
        ]
        assert route_after_consensus(state) == "draft_proposal"

    def test_max_iterations_forces_advance_to_safety(self):
        state = _base_state()
        state["iteration_count"] = 3  # equals max_iterations
        state["current_verdicts"] = [_rejected_verdict("meteorology")]
        assert route_after_consensus(state) == "review_safety"

    def test_critical_safety_rejection_goes_to_end(self):
        """Critical failure (hard constraint + DATA_UNAVAILABLE) → END."""
        from nexus.state.schemas import AgentFailureType

        state = _base_state()
        state["current_verdicts"] = [
            AgentVerdict(
                agent_name="safety",
                verdict="REJECTED",
                is_hard_constraint=True,
                confidence=1.0,
                rejection_reason="critical data unavailable",
                failure_type=AgentFailureType.DATA_UNAVAILABLE,
            )
        ]
        result = route_after_consensus(state)
        assert result == END

    def test_empty_verdicts_routes_to_redraft(self):
        """No verdicts = no approval → re-draft."""
        state = _base_state()
        state["current_verdicts"] = []
        assert route_after_consensus(state) == "draft_proposal"


class TestRouteAfterSafety:
    def test_approved_routes_to_synthesize(self):
        state = _base_state()
        state["current_verdicts"] = [_approved_verdict("safety")]
        assert route_after_safety(state) == "safe"

    def test_rejected_routes_to_end(self):
        state = _base_state()
        state["current_verdicts"] = [_rejected_verdict("safety")]
        assert route_after_safety(state) == "unsafe"

    def test_no_safety_verdict_defaults_safe(self):
        """If safety hasn't produced a verdict yet, default to safe."""
        state = _base_state()
        state["current_verdicts"] = [_approved_verdict("meteorology")]
        assert route_after_safety(state) == "safe"
