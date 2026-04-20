"""
Meteorology review agent — deterministic threshold checks.

Tech §5.5 hard thresholds:
- precipitation_probability > 40%  → REJECTED
- AQI > 100                        → REJECTED
- lightning_risk + has_exposed_sections → REJECTED
- activity ends < 30 min before sunset  → REJECTED
"""

from __future__ import annotations

import logging
from datetime import timedelta

from nexus.agents.error_boundary import agent_error_boundary
from nexus.state.graph_state import WeekendPlanState
from nexus.state.schemas import AgentVerdict
from nexus.tools.models import DaylightWindow, WeatherForecast

logger = logging.getLogger(__name__)

PRECIP_THRESHOLD = 40.0  # percent
AQI_THRESHOLD = 100
SUNSET_BUFFER_MINUTES = 30


@agent_error_boundary("meteorology", is_hard_constraint=True)
async def meteorology_review(state: WeekendPlanState) -> dict:
    """
    Fetch weather data and run deterministic safety thresholds.

    Returns: current_verdicts, weather_data, negotiation_log
    """
    registry = state["tool_registry"]
    proposal = state["primary_activity"]

    if proposal is None:
        return _approved("meteorology", "No proposal to review yet")

    coordinates = proposal.location_coordinates
    target_date = state["target_date"]

    # ── Fetch data ─────────────────────────────────────────────────────────
    from datetime import datetime, timezone
    import asyncio

    weather_tool = registry.weather
    forecast, aqi, daylight = await asyncio.gather(
        weather_tool.get_forecast(coordinates, datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)),
        weather_tool.get_air_quality(coordinates),
        weather_tool.get_daylight_window(coordinates, target_date),
    )

    # Attach nested objects
    forecast.aqi = aqi
    forecast.daylight = daylight

    # ── Threshold checks ───────────────────────────────────────────────────
    rejections: list[str] = []

    if forecast.precipitation_probability > PRECIP_THRESHOLD:
        rejections.append(
            f"Rain probability {forecast.precipitation_probability:.0f}% exceeds {PRECIP_THRESHOLD:.0f}% threshold"
        )

    if aqi.aqi > AQI_THRESHOLD:
        rejections.append(f"Air quality index {aqi.aqi} exceeds {AQI_THRESHOLD} threshold")

    if forecast.lightning_risk and proposal.has_exposed_sections:
        rejections.append("Lightning risk with exposed trail sections — unsafe conditions")

    # Sunset check: estimate return time
    if daylight.sunset:
        activity_end = proposal.start_time + timedelta(hours=proposal.estimated_duration_hours)
        latest_end = daylight.sunset - timedelta(minutes=SUNSET_BUFFER_MINUTES)
        if activity_end > latest_end:
            rejections.append(
                f"Activity ends at {activity_end.strftime('%H:%M')} — "
                f"within {SUNSET_BUFFER_MINUTES} minutes of sunset ({daylight.sunset.strftime('%H:%M')})"
            )

    if rejections:
        suggestion = _suggest_alternative_window(forecast, daylight)
        return {
            "current_verdicts": [
                AgentVerdict(
                    agent_name="meteorology",
                    verdict="REJECTED",
                    is_hard_constraint=True,
                    confidence=1.0,
                    rejection_reason="; ".join(rejections),
                    recommendation=suggestion,
                )
            ],
            "weather_data": forecast,
            "negotiation_log": [f"meteorology: REJECTED — {'; '.join(rejections)}"],
        }

    return {
        "current_verdicts": [
            AgentVerdict(
                agent_name="meteorology",
                verdict="APPROVED",
                is_hard_constraint=True,
                confidence=1.0,
                details={
                    "precipitation_probability": forecast.precipitation_probability,
                    "aqi": aqi.aqi,
                    "conditions": forecast.conditions_text,
                },
            )
        ],
        "weather_data": forecast,
        "negotiation_log": [
            f"meteorology: APPROVED — {forecast.conditions_text}, "
            f"precip {forecast.precipitation_probability:.0f}%, AQI {aqi.aqi}"
        ],
    }


def _suggest_alternative_window(forecast: WeatherForecast, daylight: DaylightWindow) -> str:
    """
    Generate a concrete revision recommendation for the objective agent.

    Returns a plain-English suggestion string placed in AgentVerdict.recommendation.
    Never shown directly to the user — feeds the revision strategy in task 5.9.
    """
    suggestions = []

    if forecast.precipitation_probability > PRECIP_THRESHOLD:
        suggestions.append(
            "Consider early morning start (before 9am) when precipitation probability is lower"
        )

    if forecast.aqi and forecast.aqi.aqi > AQI_THRESHOLD:
        suggestions.append(
            "Consider a coastal or lower-elevation alternative route"
        )

    if daylight.sunset:
        latest_start = daylight.sunset - timedelta(
            minutes=SUNSET_BUFFER_MINUTES + 60 * 6  # assume ~6hr activity
        )
        suggestions.append(
            f"Start no later than {latest_start.strftime('%H:%M')} to return before sunset"
        )

    return "; ".join(suggestions)


def _approved(agent_name: str, reason: str) -> dict:
    return {
        "current_verdicts": [
            AgentVerdict(
                agent_name=agent_name,
                verdict="APPROVED",
                is_hard_constraint=True,
                confidence=1.0,
                details={"reason": reason},
            )
        ],
        "weather_data": None,
        "negotiation_log": [f"{agent_name}: APPROVED — {reason}"],
    }
