"""
Jinja2-backed Markdown renderer for plan files — Tech §14.

`render_plan_markdown(state, narrative_text)` renders `plan.md.j2`
and returns the Markdown string written to ~/.nexus/plans/.

Includes YAML frontmatter: date, activity, status, request_id.

Also exposes `markdown_to_html()` for converting saved .md plan files
back to HTML for display at GET /plans/{id}.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import jinja2

if TYPE_CHECKING:
    from nexus.state.graph_state import WeekendPlanState

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
    undefined=jinja2.StrictUndefined,
    autoescape=False,  # Markdown — no HTML escaping
)


def render_plan_markdown(state: "WeekendPlanState", narrative_text: str) -> str:
    """Render plan.md.j2 with plan state → Markdown string."""
    from nexus.output.html import _build_context, _build_timeline
    from nexus.output.renderer import _parse_narrative

    proposal = state.get("primary_activity")
    meal = state.get("meal_plan")
    routes = state.get("route_data") or {}
    target_date = state.get("target_date")
    request_id = state.get("request_id", "")
    confidence_labels = state.get("output_confidence_labels") or []
    backup = state.get("backup_activity")

    if proposal is None:
        return "---\nstatus: unavailable\n---\n\n# Plan unavailable\n"

    why_text, day_text = _parse_narrative(narrative_text)
    timeline = _build_timeline(proposal, meal, routes)

    ctx = {
        "plan": {
            "request_id": request_id,
            "target_date": target_date.isoformat() if target_date else "unknown",
            "activity_name": proposal.activity_name,
            "estimated_duration_hours": proposal.estimated_duration_hours,
            "start_time": proposal.start_time.strftime("%-I:%M %p") if proposal.start_time else None,
            "why_this_plan": why_text,
            "day_narrative": day_text,
            "timeline": timeline,
            "backup_activity": backup,
            "backup_summary": None,
            "preparation_checklist": [
                "Check trail/route conditions before departing",
                "Pack water and food for the full activity",
            ],
            "emergency_info": "Call 911 in an emergency",
        },
        "confidence_labels": (
            [{"type": k, "text": v} for k, v in confidence_labels.items()]
            if isinstance(confidence_labels, dict)
            else [{"type": cl.confidence, "text": cl.label} for cl in confidence_labels]
            if confidence_labels
            else []
        ),
    }

    template = _env.get_template("plan.md.j2")
    return template.render(**ctx)


def markdown_to_html(markdown_text: str) -> str:
    """
    Convert a saved Markdown plan file to HTML for browser display.

    Uses the `markdown` package (PyPI: `Markdown`, imported as `import markdown`).
    """
    import markdown  # type: ignore[import-untyped]

    return markdown.markdown(
        markdown_text,
        extensions=["meta", "tables", "fenced_code"],
    )
