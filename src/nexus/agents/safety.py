"""
Safety review agent — final hard gate before plan synthesis.

Tech §5.9 checks:
- Remote location (no hospital within 30mi) + family + marginal weather → REJECTED
- Post-sunset return home
- Route coverage heuristic: >50% poor coverage → REJECTED
"""

from __future__ import annotations

import logging
from datetime import timedelta

from nexus.agents.error_boundary import agent_error_boundary
from nexus.state.graph_state import WeekendPlanState
from nexus.state.schemas import AgentVerdict

logger = logging.getLogger(__name__)

HOSPITAL_SEARCH_RADIUS_MILES = 30.0
MARGINAL_WEATHER_PRECIP_THRESHOLD = 30.0  # lower than meteorology's 40%
MAX_COVERAGE_POOR_PERCENT = 50.0
SUNSET_BUFFER_MINUTES = 30


@agent_error_boundary("safety", is_hard_constraint=True)
async def safety_review(state: WeekendPlanState) -> dict:
    """
    Final safety gate — composite risk assessment.

    Returns: current_verdicts, negotiation_log
    """
    proposal = state["primary_activity"]
    if proposal is None:
        return _approved_verdict("No proposal to evaluate")

    weather = state["weather_data"]
    family_profile = state["family_profile"]
    route_data = state.get("route_data") or {}
    registry = state["tool_registry"]

    # ── Read configurable thresholds ────────────────────────────────────────
    from nexus.config import NexusConfig
    _config = state.get("config")
    if isinstance(_config, NexusConfig):
        _marginal_precip = float(_config.planning.marginal_weather_precip_pct)
        _hospital_radius = _config.planning.hospital_search_radius_miles
        _sunset_buffer = _config.planning.min_sunset_buffer_minutes
    else:
        _marginal_precip = MARGINAL_WEATHER_PRECIP_THRESHOLD
        _hospital_radius = HOSPITAL_SEARCH_RADIUS_MILES
        _sunset_buffer = SUNSET_BUFFER_MINUTES

    rejections: list[str] = []

    # ── Hospital proximity check ───────────────────────────────────────────
    # Only runs if family is present AND weather is marginal (avoid Overpass call otherwise)
    has_family = family_profile is not None and len(getattr(family_profile, "members", [])) > 0
    marginal_weather = (
        weather is not None
        and weather.precipitation_probability > _marginal_precip
    )
    is_remote = False
    if has_family and marginal_weather:
        _hospital_result = await registry.activity.search_activities(
            proposal.location_coordinates,
            _hospital_radius,
            ["hospital", "emergency"],
        )
        # search_activities returns (list, data_source) tuple — unpack
        nearby_hospitals, _ = _hospital_result
        is_remote = len(nearby_hospitals) == 0

    if is_remote and has_family and marginal_weather:
        rejections.append(
            "Remote location with family and marginal weather — "
            f"no hospital within {_hospital_radius:.0f} miles, "
            f"precip {weather.precipitation_probability:.0f}%"
        )

    # ── Post-sunset return check ───────────────────────────────────────────
    if weather and weather.daylight and weather.daylight.sunset:
        restaurant_to_home = route_data.get("restaurant_to_home")
        driving_home_min = restaurant_to_home.duration_minutes if restaurant_to_home else 60.0

        estimated_return = (
            proposal.start_time
            + timedelta(hours=proposal.estimated_duration_hours)
            + timedelta(minutes=driving_home_min)
        )
        # Normalise both sides to naive datetimes for comparison (strip tzinfo if present)
        estimated_return_naive = estimated_return.replace(tzinfo=None) if estimated_return.tzinfo else estimated_return
        sunset_dt = weather.daylight.sunset
        sunset_naive = sunset_dt.replace(tzinfo=None) if sunset_dt.tzinfo else sunset_dt
        sunset_deadline = sunset_naive - timedelta(minutes=_sunset_buffer)

        if estimated_return_naive > sunset_deadline:
            rejections.append(
                f"Estimated return home ({estimated_return_naive.strftime('%H:%M')}) "
                f"is after sunset buffer ({sunset_deadline.strftime('%H:%M')})"
            )

    # ── Route cell coverage check (only a hard gate if user requires cell coverage) ───
    if proposal.require_cell_coverage:
        from nexus.tools.providers.coverage import estimate_cell_coverage

        coverage = await estimate_cell_coverage(proposal.location_coordinates, registry.routing)
        if coverage.poor_coverage_percentage > MAX_COVERAGE_POOR_PERCENT:
            rejections.append(
                f"Poor cell coverage along route ({coverage.poor_coverage_percentage:.0f}% of route) "
                f"— cell coverage required for this plan"
            )

    if rejections:
        return {
            "current_verdicts": [
                AgentVerdict(
                    agent_name="safety",
                    verdict="REJECTED",
                    is_hard_constraint=True,
                    confidence=1.0,
                    rejection_reason="; ".join(rejections),
                )
            ],
            "negotiation_log": [f"safety: REJECTED — {'; '.join(rejections)}"],
        }

    return {
        "current_verdicts": [
            AgentVerdict(
                agent_name="safety",
                verdict="APPROVED",
                is_hard_constraint=True,
                confidence=1.0,
                details={
                    "is_remote": is_remote,
                    "marginal_weather": marginal_weather,
                    "coverage_ok": not proposal.require_cell_coverage,
                },
            )
        ],
        "negotiation_log": ["safety: APPROVED — all safety checks passed"],
    }


def _approved_verdict(reason: str) -> dict:
    return {
        "current_verdicts": [
            AgentVerdict(
                agent_name="safety",
                verdict="APPROVED",
                is_hard_constraint=True,
                confidence=1.0,
                details={"reason": reason},
            )
        ],
        "negotiation_log": [f"safety: APPROVED — {reason}"],
    }
