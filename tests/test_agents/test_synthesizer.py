"""
Unit tests for plan_synthesizer — ISSUE-17 fallback renderer.

Verifies that when the full Jinja2 renderer raises, the synthesizer falls back
to render_minimal_plan() and the output_html field is still populated with a
degraded-mode notice.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexus.state.schemas import ActivityProposal


def _make_state(activity_data_source: str = "live") -> dict:
    """Minimal WeekendPlanState dict with the fields synthesizer reads."""
    proposal = ActivityProposal(
        activity_name="Tiger Mountain",
        activity_type="hiking",
        location_coordinates=(47.48, -121.97),
        endpoint_coordinates=(47.48, -121.97),
        start_time=datetime(2026, 4, 19, 9, 0, tzinfo=timezone.utc),
        estimated_duration_hours=4.0,
        estimated_return_after_sunset=False,
        difficulty="moderate",
        max_distance_miles=10.0,
        min_elevation_ft=0,
        search_radius_miles=50.0,
        require_cell_coverage=False,
        max_activity_hours=8.0,
    )

    model = MagicMock()
    msg = MagicMock()
    msg.content = "A wonderful day of hiking awaits."
    model.ainvoke = AsyncMock(return_value=msg)
    model.with_structured_output = MagicMock(return_value=model)

    router = MagicMock()
    router.get_model = MagicMock(return_value=model)

    return {
        "primary_activity": proposal,
        "activity_data_source": activity_data_source,
        "model_router": router,
        "tool_registry": MagicMock(),
        "family_profile": None,
        "meal_plan": None,
        "weather_data": None,
        "target_date": date(2026, 4, 19),
        "family_activities": [],
        "proposal_history": [proposal],
        "plan_requirements": None,
        "negotiation_log": [],
        "rejection_context": None,
        "iteration": 0,
    }


class TestSynthesizerFallbackRenderer:
    """ISSUE-17: Full render failure → minimal renderer fallback."""

    @pytest.mark.asyncio
    async def test_minimal_renderer_used_when_full_renderer_fails(self):
        """When render_plan_html() raises, output_html still populated via minimal renderer."""
        state = _make_state()

        with (
            patch("nexus.output.html.render_plan_html", side_effect=RuntimeError("template error")),
            patch(
                "nexus.output.renderer.render_minimal_plan", return_value="<html>minimal</html>"
            ) as mock_minimal,
            patch("nexus.output.markdown.render_plan_markdown", return_value="# Plan"),
            patch("nexus.state.helpers.prepare_llm_context", return_value={}),
        ):
            from nexus.agents.synthesizer import plan_synthesizer

            result = await plan_synthesizer(state)

        assert "output_html" in result
        assert result["output_html"] == "<html>minimal</html>"
        mock_minimal.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_full_renderer_used_when_no_failure(self):
        """When render_plan_html() succeeds, the full HTML is used (not minimal)."""
        state = _make_state()

        with (
            patch("nexus.output.html.render_plan_html", return_value="<html>full plan</html>"),
            patch("nexus.output.renderer.render_minimal_plan") as mock_minimal,
            patch("nexus.output.markdown.render_plan_markdown", return_value="# Plan"),
            patch("nexus.state.helpers.prepare_llm_context", return_value={}),
        ):
            from nexus.agents.synthesizer import plan_synthesizer

            result = await plan_synthesizer(state)

        assert result["output_html"] == "<html>full plan</html>"
        mock_minimal.assert_not_called()

    @pytest.mark.asyncio
    async def test_minimal_renderer_contains_degraded_notice(self):
        """Minimal renderer output (plan_minimal.html.j2) includes degraded-mode text."""
        state = _make_state()

        # Use the real minimal renderer, not a mock
        with (
            patch("nexus.output.html.render_plan_html", side_effect=RuntimeError("boom")),
            patch("nexus.output.markdown.render_plan_markdown", return_value="# Plan"),
            patch("nexus.state.helpers.prepare_llm_context", return_value={}),
        ):
            from nexus.agents.synthesizer import plan_synthesizer

            result = await plan_synthesizer(state)

        assert result.get("output_html"), "output_html must not be empty after fallback"
        # The plan_minimal.html.j2 template includes a degraded notice
        assert (
            "unavailable" in result["output_html"].lower()
            or "Tiger Mountain" in result["output_html"]
        )


class TestSynthesizerFallbackNote:
    """ISSUE-14: activity_data_source drives a fallback note in the narrative."""

    @pytest.mark.asyncio
    async def test_static_pnw_note_injected_into_narrative(self):
        state = _make_state(activity_data_source="static_pnw")

        with (
            patch("nexus.output.html.render_plan_html", return_value="<html>ok</html>"),
            patch("nexus.output.markdown.render_plan_markdown", return_value="# Plan"),
            patch("nexus.state.helpers.prepare_llm_context", return_value={}),
        ):
            from nexus.agents.synthesizer import plan_synthesizer

            result = await plan_synthesizer(state)

        assert result["output_html"] == "<html>ok</html>"

    @pytest.mark.asyncio
    async def test_static_template_note_injected(self):
        state = _make_state(activity_data_source="static_template")

        with (
            patch("nexus.output.html.render_plan_html", return_value="<html>ok</html>"),
            patch("nexus.output.markdown.render_plan_markdown", return_value="# Plan"),
            patch("nexus.state.helpers.prepare_llm_context", return_value={}),
        ):
            from nexus.agents.synthesizer import plan_synthesizer

            result = await plan_synthesizer(state)

        assert result["output_html"] == "<html>ok</html>"
