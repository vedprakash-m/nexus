"""
Tests for orchestrator agents — tasks 5.15.

orchestrator_check_consensus() is deterministic — no mocking needed.
orchestrator_parse_intent() uses LLM — mock with_structured_output.

Schema-validation tests: assert output conforms to Pydantic model.
Do NOT assert on specific LLM text — it varies.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_agents.test_meteorology import _make_proposal, _make_state


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _verdict(agent_name: str, result: str = "APPROVED") -> object:
    from nexus.state.schemas import AgentVerdict

    return AgentVerdict(
        agent_name=agent_name,
        verdict=result,  # type: ignore[arg-type]
        is_hard_constraint=True,
        confidence=1.0,
    )


def _mock_llm_for(pydantic_model: type) -> MagicMock:
    """Build a mock model whose .with_structured_output returns an AsyncMock LLM."""
    structured_mock = AsyncMock()
    model_mock = MagicMock()
    model_mock.with_structured_output.return_value = structured_mock
    return model_mock, structured_mock


# ─────────────────────────────────────────────────────────────────────────────
# orchestrator_check_consensus() — deterministic, no LLM
# ─────────────────────────────────────────────────────────────────────────────


class TestOrchestratorConsensus:
    async def test_all_approved_moves_to_validating(self):
        """All verdicts APPROVED → current_phase = 'validating'."""
        from nexus.agents.orchestrator import orchestrator_check_consensus

        state = _make_state()
        # all_agents_approved() requires meteorology, family_coordinator, nutritional, logistics
        state["current_verdicts"] = [
            _verdict("meteorology", "APPROVED"),
            _verdict("logistics", "APPROVED"),
            _verdict("family_coordinator", "APPROVED"),
            _verdict("nutritional", "APPROVED"),
        ]
        state["iteration_count"] = 0
        state["pending_constraints"] = []

        result = await orchestrator_check_consensus(state)

        assert result["current_phase"] == "validating"
        assert result["iteration_count"] == 1
        assert result["rejection_context"] is None

    async def test_rejections_move_to_revising(self):
        """Any REJECTED verdict → current_phase = 'revising'."""
        from nexus.agents.orchestrator import orchestrator_check_consensus

        state = _make_state()
        state["current_verdicts"] = [
            _verdict("meteorology", "REJECTED"),
            _verdict("logistics", "APPROVED"),
        ]
        state["iteration_count"] = 0
        state["pending_constraints"] = []

        result = await orchestrator_check_consensus(state)

        assert result["current_phase"] == "revising"
        assert result["rejection_context"] is not None
        assert "meteorology" in result["rejection_context"]

    async def test_max_iterations_forces_validating(self):
        """
        Even with rejections, reaching max_iterations forces 'validating'.
        (Graph then falls through to synthesize_plan with best effort.)
        """
        from nexus.agents.orchestrator import orchestrator_check_consensus

        state = _make_state()
        state["current_verdicts"] = [
            _verdict("meteorology", "REJECTED"),
        ]
        state["iteration_count"] = 2  # next increment = 3 == max_iterations
        state["max_iterations"] = 3
        state["pending_constraints"] = []

        result = await orchestrator_check_consensus(state)

        assert result["current_phase"] == "validating"
        assert result["iteration_count"] == 3

    async def test_pending_constraint_drains_queue(self):
        """
        Non-empty pending_constraints → queue drained, phase = 'revising',
        rejection_context updated with constraint text.
        """
        from nexus.agents.orchestrator import orchestrator_check_consensus

        state = _make_state()
        state["current_verdicts"] = [_verdict("meteorology", "APPROVED")]
        state["iteration_count"] = 0
        state["pending_constraints"] = ["avoid crowds", "no exposed ridge"]

        result = await orchestrator_check_consensus(state)

        assert result["current_phase"] == "revising"
        assert result["pending_constraints"] == []
        assert "avoid crowds" in result["rejection_context"]
        assert "no exposed ridge" in result["rejection_context"]

    async def test_single_pending_constraint_drains(self):
        """Single constraint is drained and embedded in rejection_context."""
        from nexus.agents.orchestrator import orchestrator_check_consensus

        state = _make_state()
        state["current_verdicts"] = []
        state["iteration_count"] = 0
        state["pending_constraints"] = ["kid-friendly"]

        result = await orchestrator_check_consensus(state)

        assert result["pending_constraints"] == []
        assert "kid-friendly" in result["rejection_context"]

    async def test_iteration_count_increments(self):
        """iteration_count always increments by 1."""
        from nexus.agents.orchestrator import orchestrator_check_consensus

        state = _make_state()
        state["current_verdicts"] = []
        state["iteration_count"] = 4
        state["pending_constraints"] = []

        result = await orchestrator_check_consensus(state)

        assert result["iteration_count"] == 5

    async def test_negotiation_log_populated(self):
        """negotiation_log must be non-empty."""
        from nexus.agents.orchestrator import orchestrator_check_consensus

        state = _make_state()
        state["current_verdicts"] = []
        state["iteration_count"] = 0
        state["pending_constraints"] = []

        result = await orchestrator_check_consensus(state)

        assert "negotiation_log" in result
        assert len(result["negotiation_log"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# orchestrator_parse_intent() — LLM-backed, schema validation only
# ─────────────────────────────────────────────────────────────────────────────


class TestOrchestratorParseIntent:
    async def test_returns_schema_valid_plan_requirements(self):
        """LLM returns JSON — result parsed into PlanRequirements stored in state."""
        import json
        from nexus.agents.orchestrator import orchestrator_parse_intent
        from nexus.state.schemas import PlanRequirements, UserProfile

        # New implementation uses model.bind(...).ainvoke(messages)
        llm_json = json.dumps({"activity_types": ["hiking"], "max_distance_miles": 30.0,
                                "family_friendly": True})
        bound_model = MagicMock()
        bound_model.ainvoke = AsyncMock(return_value=MagicMock(content=llm_json))

        mock_model = MagicMock()
        mock_model.bind.return_value = bound_model

        mock_router = MagicMock()
        mock_router.get_model.return_value = mock_model

        state = _make_state()
        state["model_router"] = mock_router
        state["user_intent"] = "hike with kids near the bay"
        state["user_profile"] = UserProfile(
            fitness_level="intermediate",
            max_driving_minutes=90,
            preferred_activities=["hiking"],
        )
        state["family_profile"] = None

        result = await orchestrator_parse_intent(state)

        assert "plan_requirements" in result
        req = result["plan_requirements"]
        assert isinstance(req, PlanRequirements)
        assert "hiking" in req.activity_types
        assert req.max_distance_miles == 30.0

    async def test_model_bind_called_with_json_format(self):
        """model.bind must be called with format='json' (no schema enforcement)."""
        import json
        from nexus.agents.orchestrator import orchestrator_parse_intent
        from nexus.state.schemas import UserProfile

        bound_model = MagicMock()
        bound_model.ainvoke = AsyncMock(
            return_value=MagicMock(content=json.dumps({"activity_types": ["cycling"]}))
        )
        mock_model = MagicMock()
        mock_model.bind.return_value = bound_model

        mock_router = MagicMock()
        mock_router.get_model.return_value = mock_model

        state = _make_state()
        state["model_router"] = mock_router
        state["user_intent"] = "bike ride"
        state["user_profile"] = UserProfile()
        state["family_profile"] = None

        await orchestrator_parse_intent(state)

        mock_model.bind.assert_called_once()
        call_kwargs = mock_model.bind.call_args.kwargs
        assert call_kwargs.get("format") == "json"

    async def test_phase_set_to_drafting(self):
        """After parsing, current_phase must be 'drafting'."""
        from nexus.agents.orchestrator import orchestrator_parse_intent
        from nexus.state.schemas import PlanRequirements, UserProfile

        mock_requirements = PlanRequirements()
        structured_llm = AsyncMock(return_value=mock_requirements)
        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = structured_llm
        mock_router = MagicMock()
        mock_router.get_model.return_value = mock_model

        state = _make_state()
        state["model_router"] = mock_router
        state["user_intent"] = "outdoor picnic"
        state["user_profile"] = UserProfile()
        state["family_profile"] = None

        result = await orchestrator_parse_intent(state)

        assert result["current_phase"] == "drafting"

    async def test_error_boundary_on_llm_timeout(self):
        """asyncio.TimeoutError from LLM is caught by error boundary — state unchanged."""
        import asyncio

        from nexus.agents.orchestrator import orchestrator_parse_intent
        from nexus.state.schemas import UserProfile

        structured_llm = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = structured_llm
        mock_router = MagicMock()
        mock_router.get_model.return_value = mock_model

        state = _make_state()
        state["model_router"] = mock_router
        state["user_intent"] = "hike"
        state["user_profile"] = UserProfile()
        state["family_profile"] = None

        # Error boundary catches the timeout — should return a partial state, not raise
        result = await orchestrator_parse_intent(state)

        # Error boundary always returns a dict (never raises)
        assert isinstance(result, dict)
