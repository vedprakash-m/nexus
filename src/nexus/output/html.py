"""
Jinja2-backed HTML renderer for plan pages — Tech §9.4.

`render_plan_html(state, narrative_text)` renders the full `plan.html.j2`
template with all state fields mapped to template variables.

UX §1.3 filter enforced: no agent names, scores, or iteration counts
are passed to the template context.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import jinja2

if TYPE_CHECKING:
    from nexus.state.graph_state import WeekendPlanState

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
    undefined=jinja2.StrictUndefined,
    autoescape=jinja2.select_autoescape(["html"]),
)


def render_plan_html(state: "WeekendPlanState", narrative_text: str) -> str:
    """
    Render `plan.html.j2` with plan state.

    Builds a safe template context — internal fields (agent names, confidence
    scores, iteration counts) are excluded from the context entirely.
    """
    ctx = _build_context(state, narrative_text)
    template = _env.get_template("plan.html.j2")
    return template.render(**ctx)


def render_page(template_name: str, **kwargs) -> str:
    """Render any named template with provided context."""
    template = _env.get_template(template_name)
    return template.render(**kwargs)


def _build_context(state: "WeekendPlanState", narrative_text: str) -> dict:
    """
    Map WeekendPlanState to plan.html.j2 template variables.

    Only user-facing fields are included (UX §1.3).
    """
    from nexus.output.renderer import _parse_narrative

    proposal = state.get("primary_activity")
    meal = state.get("meal_plan")
    weather = state.get("weather_data")
    routes = state.get("route_data") or {}
    target_date = state.get("target_date")
    family_activities = state.get("family_activities") or []
    confidence_labels = state.get("output_confidence_labels") or []
    request_id = state.get("request_id", "")
    backup = state.get("backup_activity")

    if proposal is None:
        return {
            "request_id": request_id,
            "plan": None,
            "confidence_labels": [],
        }

    why_text, day_text = _parse_narrative(narrative_text)

    # Build timeline from proposal + meal
    timeline = _build_timeline(proposal, meal, routes)

    # Determine meal section label from timeline
    meal_section_label = "Meal"
    for item in timeline:
        label = item.get("label", "")
        if "Breakfast at" in label:
            meal_section_label = "Breakfast"
        elif "Lunch at" in label:
            meal_section_label = "Lunch"
        elif "Dinner at" in label:
            meal_section_label = "Dinner"

    # Verdict flags (no percentages — boolean only)
    weather_ok = (
        weather is not None
        and weather.precipitation_probability <= 40
        and (weather.aqi is None or weather.aqi.aqi <= 100)
    )
    route_ok = not any(
        (r.duration_minutes or 0) > 60 for r in routes.values() if hasattr(r, "duration_minutes")
    )
    family_ok = True  # synthesizer only runs when family approved

    plan_ctx = {
        "request_id": request_id,
        "activity_name": proposal.activity_name,
        "target_date": target_date.strftime("%A, %B %-d") if target_date else "This weekend",
        "estimated_duration_hours": proposal.estimated_duration_hours,
        "start_time": proposal.start_time.strftime("%-I:%M %p") if proposal.start_time else None,
        "weather_summary": _weather_summary(weather),
        "driving_summary": _driving_distance(routes),
        "why_this_plan": why_text,
        "day_narrative": day_text,
        "tradeoff_summary": None,  # Populated by Phase 9 compromised-plan rendering
        "is_unsafe": False,
        "blocking_reasons": [],
        "downscaled_alternative": None,
        "next_weekend_forecast": None,
        "is_compromised": False,
        "timeline": timeline,
        "backup_activity": backup,
        "backup_summary": _backup_summary(proposal, backup),
        "preparation_checklist": _prep_checklist(proposal, weather),
        "emergency_info": _emergency_info(state),
        "meal_section_label": meal_section_label,
        "weather_ok": weather_ok,
        "family_ok": family_ok,
        "route_ok": route_ok,
        "family_activities": [
            {"member_name": fa.member_name, "activity_name": fa.activity_name, "location_name": getattr(fa, "location_name", "")}
            for fa in family_activities
        ],
    }

    return {
        "request_id": request_id,
        "plan": plan_ctx,
        "confidence_labels": (
            [{"type": k, "text": v} for k, v in confidence_labels.items()]
            if isinstance(confidence_labels, dict)
            else [{"type": cl.confidence, "text": cl.label} for cl in confidence_labels]
            if confidence_labels
            else []
        ),
    }


def _build_timeline(proposal, meal, routes: dict) -> list[dict]:
    """Build day timeline from activity + optional meal."""
    items = []
    if proposal.start_time:
        start = proposal.start_time
        # Departure
        route = routes.get("home_to_activity")
        if route and hasattr(route, "duration_minutes"):
            dep_dt = start - __import__("datetime").timedelta(minutes=route.duration_minutes)
            items.append({"time": dep_dt.strftime("%-I:%M %p"), "label": "Depart home", "who": None})
        items.append({"time": start.strftime("%-I:%M %p"), "label": f"Arrive at {proposal.activity_name}", "who": None})

        # Activity end
        from datetime import timedelta
        end = start + timedelta(hours=proposal.estimated_duration_hours)
        items.append({"time": end.strftime("%-I:%M %p"), "label": "Activity ends", "who": None})

        # Meal — schedule after activity + drive to restaurant
        if meal and hasattr(meal, "name"):
            from datetime import timedelta as td
            # Add travel time from trail to restaurant (use route if available)
            trail_to_restaurant = routes.get("activity_to_restaurant")
            travel_min = trail_to_restaurant.duration_minutes if trail_to_restaurant and hasattr(trail_to_restaurant, "duration_minutes") else 20.0
            meal_time = end + td(minutes=travel_min)

            # Pick label based on time of day
            hour = meal_time.hour
            if hour < 11:
                meal_label = "Breakfast"
            elif hour < 15:
                meal_label = "Lunch"
            else:
                meal_label = "Dinner"

            items.append({"time": meal_time.strftime("%-I:%M %p"), "label": f"{meal_label} at {meal.name}", "who": None})
    return items


def _weather_summary(weather) -> str | None:
    if weather is None:
        return None
    if weather.temperature_high_f:
        return f"{weather.conditions_text}, {weather.temperature_high_f:.0f}°F"
    return weather.conditions_text


def _driving_distance(routes: dict) -> str | None:
    h2a = routes.get("home_to_activity")
    if h2a and hasattr(h2a, "duration_minutes"):
        mins = int(h2a.duration_minutes)
        return f"{mins} min"
    return None


def _backup_summary(primary, backup) -> str | None:
    if backup is None:
        return None
    if hasattr(backup, "activity_name") and backup.activity_name != primary.activity_name:
        return "A more relaxed alternative if you'd like something lower-key."
    return None


def _prep_checklist(proposal, weather) -> list[str]:
    items = ["Check trail/route conditions before departing"]
    if weather and weather.precipitation_probability > 20:
        items.append("Pack rain layer")
    if proposal and proposal.has_exposed_sections:
        items.append("Sun protection — hat and sunscreen")
    if proposal and proposal.estimated_duration_hours >= 4:
        items.append("Pack food and water for the full activity")
    return items


def _emergency_info(state) -> str | None:
    """Provide nearest emergency info if available."""
    safety = state.get("safety_data")
    if safety and hasattr(safety, "nearest_hospital"):
        h = safety.nearest_hospital
        if h:
            return f"Nearest hospital: {h.get('name', 'Unknown')} ({h.get('distance_miles', '?')} mi)"
    return "Call 911 in an emergency"
