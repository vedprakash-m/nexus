"""
Plan renderers — HTML and Markdown output generators.

Called by plan_synthesizer (task 5.12). Both take the full state and
the LLM-generated narrative text as inputs.

Rules (UX §1.3 invisible contract):
- No agent names in output
- No confidence scores or percentages
- No iteration counts
- No "APPROVED"/"REJECTED"/"NEEDS_INFO"
- Use family member names (not "your spouse")
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.state.graph_state import WeekendPlanState


def render_plan_markdown(state: "WeekendPlanState", narrative_text: str) -> str:
    """
    Render the approved plan as Markdown.

    Structure:
    # [Activity] — [Date]
    [Why this plan]
    ## Your day
    [Narrative]
    ## Family activities
    [Per-member list]
    ## Dining
    [Restaurant info]
    ## Conditions
    [Weather summary — no percentages]
    """
    proposal = state["primary_activity"]
    meal = state.get("meal_plan")
    weather = state.get("weather_data")
    family_activities = state.get("family_activities") or []
    target_date = state.get("target_date")

    if proposal is None:
        return "# Plan unavailable\n\nNo activity was selected."

    # Parse narrative JSON if it came back structured
    why_text, day_text = _parse_narrative(narrative_text)

    lines: list[str] = [
        f"# {proposal.activity_name}",
        f"**{target_date.strftime('%A, %B %-d') if target_date else 'This weekend'}**",
        "",
        why_text,
        "",
        "## Your day",
        "",
        day_text,
    ]

    if family_activities:
        lines.extend(["", "## Family activities", ""])
        for fa in family_activities:
            lines.append(f"- **{fa.member_name}**: {fa.activity_name} at {fa.location_name}")

    if meal:
        lines.extend([
            "",
            "## Dining",
            "",
            f"**{meal.name}** — {meal.cuisine_type}",
            f"{meal.address}",
        ])

    if weather:
        lines.extend([
            "",
            "## Conditions",
            "",
            f"{weather.conditions_text}, high {weather.temperature_high_f:.0f}°F",
        ])

    lines.extend(["", "---", f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*"])
    return "\n".join(lines)


def render_plan_fragment(state: "WeekendPlanState", narrative_text: str) -> str:
    """
    Render the plan as a minimal HTML fragment (embedded in plan page).

    Note: Full page layout handled by Jinja2 templates in Phase 7.
    This renders just the content div for WebSocket streaming.
    Retained for testing/debugging; production uses html.render_plan_html (full page).
    """
    import html

    proposal = state["primary_activity"]
    meal = state.get("meal_plan")
    weather = state.get("weather_data")
    family_activities = state.get("family_activities") or []
    target_date = state.get("target_date")

    if proposal is None:
        return "<div class='plan-unavailable'>No plan available</div>"

    why_text, day_text = _parse_narrative(narrative_text)

    date_str = target_date.strftime("%A, %B %-d") if target_date else "This weekend"

    parts: list[str] = [
        f'<div class="plan-card">',
        f'  <h1 class="plan-title">{html.escape(proposal.activity_name)}</h1>',
        f'  <p class="plan-date">{html.escape(date_str)}</p>',
        f'  <div class="plan-why">{html.escape(why_text)}</div>',
        f'  <div class="plan-day">',
        f'    <h2>Your day</h2>',
        f'    <p>{html.escape(day_text)}</p>',
        f'  </div>',
    ]

    if family_activities:
        parts.append('  <div class="family-activities"><h2>Family activities</h2><ul>')
        for fa in family_activities:
            parts.append(
                f'    <li><strong>{html.escape(fa.member_name)}</strong>: '
                f'{html.escape(fa.activity_name)} at {html.escape(fa.location_name)}</li>'
            )
        parts.append("  </ul></div>")

    if meal:
        parts.append(
            f'  <div class="meal-plan"><h2>Dining</h2>'
            f'<p><strong>{html.escape(meal.name)}</strong> — {html.escape(meal.cuisine_type)}<br>'
            f'{html.escape(meal.address)}</p></div>'
        )

    if weather:
        parts.append(
            f'  <div class="conditions"><h2>Conditions</h2>'
            f'<p>{html.escape(weather.conditions_text)}, '
            f'high {weather.temperature_high_f:.0f}°F</p></div>'
        )

    parts.append("</div>")
    return "\n".join(parts)


def _parse_narrative(text: str) -> tuple[str, str]:
    """
    Parse LLM narrative output. Expected JSON: {"why_this_plan": "...", "your_day_narrative": "..."}.
    Falls back gracefully if response is plain text.
    """
    import json

    try:
        data = json.loads(text)
        return (
            data.get("why_this_plan", ""),
            data.get("your_day_narrative", text),
        )
    except (json.JSONDecodeError, TypeError):
        # Plain text fallback — split at first newline
        parts = text.strip().split("\n\n", 1)
        return parts[0], parts[1] if len(parts) > 1 else text
