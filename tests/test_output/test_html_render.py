"""
HTML snapshot tests for plan templates — task 7.16.

Tests:
1. plan.html.j2 renders without errors with a full fixture state.
2. Rendered output is byte-for-byte identical to the saved baseline snapshot.
   — First run saves the snapshot. Subsequent runs compare against it.
   — Delete tests/fixtures/plan_snapshot.html to regenerate.
3. StrictUndefined raises jinja2.UndefinedError when required variable is missing.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import jinja2
import pytest

# Fixture paths
_SNAPSHOT_PATH = Path(__file__).parent.parent / "fixtures" / "plan_snapshot.html"
_FIXTURES_DIR = _SNAPSHOT_PATH.parent


# ─────────────────────────────────────────────────────────────────────────────
# Fixture state factory — all fields populated (approved plan)
# ─────────────────────────────────────────────────────────────────────────────


def _full_plan_state() -> dict:
    """Return a WeekendPlanState-compatible dict with all fields populated."""
    from nexus.state.schemas import ActivityProposal, FamilyActivity, FamilyProfile, UserProfile
    from nexus.tools.models import AirQuality, DaylightWindow, WeatherForecast

    proposal = ActivityProposal(
        activity_name="Windy Hill Preserve",
        activity_type="hiking",
        location_coordinates=(37.3622, -122.1897),
        endpoint_coordinates=(37.3700, -122.1950),
        start_time=datetime(2026, 4, 19, 9, 0, tzinfo=timezone.utc),
        estimated_duration_hours=5.0,
        difficulty="moderate",
        has_exposed_sections=False,
        max_distance_miles=10.0,
    )

    weather = WeatherForecast(
        precipitation_probability=10.0,
        lightning_risk=False,
        conditions_text="Partly cloudy with morning fog",
        temperature_high_f=68.0,
        aqi=AirQuality(aqi=42, data_age_minutes=0, confidence="verified"),
        daylight=DaylightWindow(
            sunrise=datetime(2026, 4, 19, 6, 28, tzinfo=timezone.utc),
            sunset=datetime(2026, 4, 19, 19, 52, tzinfo=timezone.utc),
            data_age_minutes=0,
            confidence="verified",
        ),
        data_age_minutes=0,
        confidence="verified",
    )

    backup = ActivityProposal(
        activity_name="Windy Hill Preserve (Relaxed)",
        activity_type="hiking",
        location_coordinates=(37.3622, -122.1897),
        endpoint_coordinates=(37.3700, -122.1950),
        start_time=datetime(2026, 4, 19, 9, 0, tzinfo=timezone.utc),
        estimated_duration_hours=4.0,
        difficulty="easy",
    )

    return {
        "request_id": "test-snapshot-2026-04-19",
        "primary_activity": proposal,
        "weather_data": weather,
        "meal_plan": None,
        "route_data": {},
        "target_date": date(2026, 4, 19),
        "family_activities": [
            FamilyActivity(
                member_name="Jamie",
                activity_name="Junior Ranger trail",
                activity_type="hiking",
                location_name="Windy Hill",
            )
        ],
        "output_confidence_labels": [],
        "backup_activity": backup,
        "user_profile": UserProfile(name="Alex"),
        "family_profile": FamilyProfile(),
        "safety_data": None,
    }


_NARRATIVE = (
    '{"why_this_plan": "Perfect spring weather and moderate terrain for the whole family.", '
    '"your_day_narrative": "Depart by 9am and reach the trailhead in under an hour. '
    'The ridge offers sweeping views of the bay."}'
)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: renders without errors
# ─────────────────────────────────────────────────────────────────────────────


class TestHtmlRender:
    def test_plan_renders_without_error(self):
        """render_plan_html() with a full fixture state must not raise."""
        from nexus.output.html import render_plan_html

        state = _full_plan_state()
        html = render_plan_html(state, _NARRATIVE)

        assert isinstance(html, str)
        assert len(html) > 500
        assert "Windy Hill Preserve" in html
        assert "<!DOCTYPE html>" in html

    def test_plan_renders_correct_activity_name(self):
        """Activity name from fixture appears in rendered HTML."""
        from nexus.output.html import render_plan_html

        state = _full_plan_state()
        html = render_plan_html(state, _NARRATIVE)

        assert "Windy Hill Preserve" in html

    def test_plan_contains_weather_summary(self):
        """Weather conditions text from fixture appears in rendered HTML."""
        from nexus.output.html import render_plan_html

        state = _full_plan_state()
        html = render_plan_html(state, _NARRATIVE)

        assert "Partly cloudy" in html

    def test_plan_renders_backup_activity(self):
        """Backup activity name appears in the rendered page."""
        from nexus.output.html import render_plan_html

        state = _full_plan_state()
        html = render_plan_html(state, _NARRATIVE)

        # Backup name includes "(Relaxed)"
        assert "Relaxed" in html

    def test_no_proposal_renders_gracefully(self):
        """Missing primary_activity renders without crashing (plan=None path).

        Template title block guards against plan=None via {% if plan %}.
        """
        from nexus.output.html import render_plan_html

        state = _full_plan_state()
        state["primary_activity"] = None
        html = render_plan_html(state, "")

        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html
        assert "Nexus" in html

    # ─────────────────────────────────────────────────────────────────────────
    # Test 2: byte-for-byte snapshot regression test
    # ─────────────────────────────────────────────────────────────────────────

    def test_snapshot_regression(self):
        """
        Render plan.html.j2 and compare byte-for-byte with saved baseline.

        First run: baseline doesn't exist → save it and pass.
        Subsequent runs: assert rendered == baseline.
        Delete tests/fixtures/plan_snapshot.html to regenerate.
        """
        from nexus.output.html import render_plan_html

        state = _full_plan_state()
        rendered = render_plan_html(state, _NARRATIVE)

        _FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

        if not _SNAPSHOT_PATH.exists():
            # First run — save the baseline
            _SNAPSHOT_PATH.write_text(rendered, encoding="utf-8")
            pytest.skip(
                f"Snapshot baseline created at {_SNAPSHOT_PATH}. "
                "Re-run tests to enable regression checking."
            )

        baseline = _SNAPSHOT_PATH.read_text(encoding="utf-8")
        assert rendered == baseline, (
            "plan.html.j2 output has changed from the saved snapshot.\n"
            f"Delete {_SNAPSHOT_PATH} and re-run to accept the new output as baseline."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Test 3: StrictUndefined catches missing template variables
    # ─────────────────────────────────────────────────────────────────────────

    def test_strict_undefined_raises_on_missing_variable(self):
        """
        render_page() with StrictUndefined raises jinja2.UndefinedError
        when a required template variable is missing.
        """
        from nexus.output.html import render_page

        with pytest.raises(jinja2.UndefinedError):
            # plan.html.j2 accesses {{ request_id }} at top level.
            # Rendering without it must raise UndefinedError.
            render_page("plan.html.j2")  # no kwargs → all vars missing

    def test_strict_undefined_not_raised_with_full_context(self):
        """Correct context causes no UndefinedError."""
        from nexus.output.html import render_plan_html

        state = _full_plan_state()
        # Must not raise
        html = render_plan_html(state, _NARRATIVE)
        assert html  # non-empty
