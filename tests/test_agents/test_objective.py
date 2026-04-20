"""
Tests for objective_draft_proposal() and _apply_revision_adjustments() — task 5.15.

LLM call mocked to return a valid ActivityProposal.
Schema validation only — do NOT assert on specific LLM text.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_agents.test_meteorology import _make_proposal, _make_state


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_activity_result(name: str = "Windy Hill Hike") -> object:
    from nexus.tools.models import ActivityResult

    return ActivityResult(
        activity_id=name.lower().replace(" ", "-"),
        name=name,
        location_coordinates=(37.36, -122.19),
        activity_type="hiking",
        difficulty="moderate",
        elevation_gain_ft=1200,
        distance_miles=6.0,
        data_age_minutes=0,
        confidence="verified",
    )


def _make_plan_requirements(**kwargs) -> object:
    from nexus.state.schemas import PlanRequirements

    defaults = dict(
        activity_types=["hiking"],
        search_radius_miles=30.0,
        max_distance_miles=20.0,
        max_activity_hours=8.0,
        require_cell_coverage=False,
    )
    defaults.update(kwargs)
    return PlanRequirements(**defaults)


def _objective_state(
    *,
    candidates: list | None = None,
    mock_proposal: object | None = None,
    rejection_context: str | None = None,
) -> dict:
    """Build state for objective agent tests."""
    import json
    from nexus.state.schemas import PlanRequirements, UserProfile

    if candidates is None:
        candidates = [_make_activity_result("Windy Hill Preserve")]

    mock_activity_tool = MagicMock()
    mock_activity_tool.search_activities = AsyncMock(return_value=candidates)

    mock_routing = MagicMock()
    mock_registry = MagicMock()
    mock_registry.activity = mock_activity_tool
    mock_registry.routing = mock_routing

    # New implementation: model.bind(...).ainvoke(messages) returns {"choice_index": 0}
    bound_model = MagicMock()
    bound_model.ainvoke = AsyncMock(
        return_value=MagicMock(content=json.dumps({"choice_index": 0, "start_hour": 9}))
    )
    mock_model = MagicMock()
    mock_model.bind.return_value = bound_model

    mock_router = MagicMock()
    mock_router.get_model.return_value = mock_model

    state = _make_state()
    state["user_profile"] = UserProfile(home_coordinates=(37.7749, -122.4194))
    state["plan_requirements"] = _make_plan_requirements()
    state["tool_registry"] = mock_registry
    state["model_router"] = mock_router
    state["rejection_context"] = rejection_context
    state["proposal_history"] = []
    return state


# ─────────────────────────────────────────────────────────────────────────────
# objective_draft_proposal() — LLM schema validation
# ─────────────────────────────────────────────────────────────────────────────


class TestObjectiveDraftProposal:
    async def test_returns_schema_valid_activity_proposal(self):
        """Mock LLM returns ActivityProposal — result stored as primary_activity."""
        from nexus.agents.objective import objective_draft_proposal
        from nexus.state.schemas import ActivityProposal

        state = _objective_state()
        result = await objective_draft_proposal(state)

        assert "primary_activity" in result
        proposal = result["primary_activity"]
        assert isinstance(proposal, ActivityProposal)

    async def test_model_bind_called_for_selection(self):
        """model.bind must be called with format='json' (index-only selection)."""
        from nexus.agents.objective import objective_draft_proposal

        state = _objective_state()
        await objective_draft_proposal(state)

        mock_model = state["model_router"].get_model.return_value
        mock_model.bind.assert_called_once()
        call_kwargs = mock_model.bind.call_args.kwargs
        assert call_kwargs.get("format") == "json"

    async def test_proposal_added_to_history(self):
        """Returned proposal is appended to proposal_history."""
        from nexus.agents.objective import objective_draft_proposal

        state = _objective_state()
        result = await objective_draft_proposal(state)

        assert "proposal_history" in result
        assert len(result["proposal_history"]) == 1

    async def test_phase_set_to_reviewing(self):
        """After drafting, current_phase = 'reviewing'."""
        from nexus.agents.objective import objective_draft_proposal

        state = _objective_state()
        result = await objective_draft_proposal(state)

        assert result.get("current_phase") == "reviewing"

    async def test_no_candidates_raises_hard_constraint(self):
        """If activity search returns empty list, raise HardConstraintDataUnavailable."""
        import pytest
        from nexus.agents.objective import objective_draft_proposal
        from nexus.resilience import HardConstraintDataUnavailable

        state = _objective_state(candidates=[])
        with pytest.raises(HardConstraintDataUnavailable) as exc_info:
            await objective_draft_proposal(state)
        assert "activity_search" in str(exc_info.value)

    async def test_aborts_without_requirements(self):
        """If plan_requirements is None, agent raises HardConstraintDataUnavailable (parse_intent failed)."""
        import pytest
        from nexus.agents.objective import objective_draft_proposal
        from nexus.resilience import HardConstraintDataUnavailable

        state = _objective_state()
        state["plan_requirements"] = None
        with pytest.raises(HardConstraintDataUnavailable) as exc_info:
            await objective_draft_proposal(state)
        assert "intent_parsing" in str(exc_info.value)

    async def test_excludes_already_proposed_candidates(self):
        """Candidates matching proposal_history names are excluded; raises when none remain."""
        import pytest
        from nexus.agents.objective import objective_draft_proposal
        from nexus.resilience import HardConstraintDataUnavailable

        previously_proposed = _make_proposal(activity_name="Windy Hill Preserve")

        state = _objective_state()
        state["proposal_history"] = [previously_proposed]
        # Activity candidate has the same name → should be excluded → 0 candidates remain
        state["tool_registry"].activity.search_activities = AsyncMock(
            return_value=[_make_activity_result("Windy Hill Preserve")]
        )

        with pytest.raises(HardConstraintDataUnavailable) as exc_info:
            await objective_draft_proposal(state)
        assert "activity_search" in str(exc_info.value)

    async def test_error_boundary_on_llm_exception(self):
        """RuntimeError from LLM is caught by error boundary."""
        from nexus.agents.objective import objective_draft_proposal

        state = _objective_state()
        state["tool_registry"].activity.search_activities = AsyncMock(
            side_effect=RuntimeError("API down")
        )

        result = await objective_draft_proposal(state)

        # Error boundary always returns a dict, never raises
        assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# _apply_revision_adjustments() — deterministic, no LLM
# ─────────────────────────────────────────────────────────────────────────────


class TestRevisionAdjustments:
    def test_logistics_radius_rejection_shrinks_radius(self):
        """'logistics' + 'radius' in rejection_context → search_radius * 0.8."""
        from nexus.agents.objective import _apply_revision_adjustments

        req = _make_plan_requirements(search_radius_miles=50.0)
        state = _make_state()
        state["rejection_context"] = "logistics: exceeds radius limit"

        adjusted = _apply_revision_adjustments(req, "logistics: exceeds radius limit", state)

        assert adjusted.search_radius_miles == pytest.approx(40.0)

    def test_cell_rejection_requires_coverage(self):
        """'cell' in rejection_context → require_cell_coverage = True."""
        from nexus.agents.objective import _apply_revision_adjustments

        req = _make_plan_requirements(require_cell_coverage=False)
        state = _make_state()

        adjusted = _apply_revision_adjustments(
            req, "family coordinator: no cell service", state
        )

        assert adjusted.require_cell_coverage is True

    def test_coverage_rejection_requires_coverage(self):
        """'coverage' keyword also triggers require_cell_coverage."""
        from nexus.agents.objective import _apply_revision_adjustments

        req = _make_plan_requirements(require_cell_coverage=False)
        state = _make_state()

        adjusted = _apply_revision_adjustments(req, "poor coverage along route", state)

        assert adjusted.require_cell_coverage is True

    def test_timeline_rejection_compresses_hours(self):
        """'timeline' or 'time' in rejection → max_activity_hours -= 0.5."""
        from nexus.agents.objective import _apply_revision_adjustments

        req = _make_plan_requirements(max_activity_hours=8.0)
        state = _make_state()

        adjusted = _apply_revision_adjustments(req, "logistics: timeline conflict too long", state)

        assert adjusted.max_activity_hours == pytest.approx(7.5)

    def test_no_matching_context_returns_unchanged(self):
        """Unrelated rejection context → requirements returned unchanged."""
        from nexus.agents.objective import _apply_revision_adjustments

        req = _make_plan_requirements(search_radius_miles=50.0, require_cell_coverage=False)
        state = _make_state()

        adjusted = _apply_revision_adjustments(req, "nutritional: no restaurant found", state)

        assert adjusted.search_radius_miles == pytest.approx(50.0)
        assert adjusted.require_cell_coverage is False

    def test_returns_new_instance_not_mutation(self):
        """model_copy must return a new instance — original is unchanged."""
        from nexus.agents.objective import _apply_revision_adjustments

        req = _make_plan_requirements(search_radius_miles=50.0)
        state = _make_state()

        adjusted = _apply_revision_adjustments(req, "logistics: radius exceeded", state)

        # Original unchanged
        assert req.search_radius_miles == pytest.approx(50.0)
        # New instance has update
        assert adjusted.search_radius_miles == pytest.approx(40.0)
        assert adjusted is not req
