"""
Logistics review agent — deterministic driving time + timeline checks.

Tech §5.8 checks:
- total driving time vs family max_total_driving_minutes
- departure before 6am
- full day > 12 hours
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from nexus.agents.error_boundary import agent_error_boundary
from nexus.state.graph_state import WeekendPlanState
from nexus.state.schemas import AgentVerdict
from nexus.tools.models import RouteResult

logger = logging.getLogger(__name__)

MEAL_DURATION_MINUTES = 60
MAX_ACCEPTABLE_DAY_HOURS = 12
EARLIEST_DEPARTURE_HOUR = 6


@agent_error_boundary("logistics", is_hard_constraint=True)
async def logistics_review(state: WeekendPlanState) -> dict:
    """
    Calculate routes and verify logistics fit within family constraints.

    Returns: current_verdicts, route_data, negotiation_log
    """
    proposal = state["primary_activity"]
    family_profile = state["family_profile"]

    if proposal is None:
        return _approved_verdict("No proposal to route yet")

    home = state["user_profile"].home_coordinates
    activity_loc = proposal.location_coordinates
    endpoint = proposal.endpoint_coordinates
    meal_plan = state["meal_plan"]

    routing = state["tool_registry"].routing

    # ── Fetch routes in parallel ───────────────────────────────────────────
    route_home_to_activity, route_activity_to_home = await asyncio.gather(
        routing.get_route(home, activity_loc),
        routing.get_route(endpoint, home),
    )

    # Restaurant route is optional (meal_plan may not exist yet)
    route_activity_to_restaurant: RouteResult | None = None
    route_restaurant_to_home: RouteResult | None = None

    if meal_plan:
        meal_coords = meal_plan.coordinates
        route_activity_to_restaurant, route_restaurant_to_home = await asyncio.gather(
            routing.get_route(endpoint, meal_coords),
            routing.get_route(meal_coords, home),
        )

    # ── Total driving time ─────────────────────────────────────────────────
    total_driving = route_home_to_activity.duration_minutes + route_activity_to_home.duration_minutes
    if route_activity_to_restaurant and route_restaurant_to_home:
        total_driving = (
            route_home_to_activity.duration_minutes
            + route_activity_to_restaurant.duration_minutes
            + route_restaurant_to_home.duration_minutes
        )

    max_driving = family_profile.max_total_driving_minutes if family_profile else 120

    # ── Timeline conflict checks ───────────────────────────────────────────
    conflicts = _detect_timeline_conflicts(
        state,
        route_home_to_activity,
        route_activity_to_restaurant,
        route_restaurant_to_home or route_activity_to_home,
    )

    route_data = {
        "home_to_activity": route_home_to_activity,
        "activity_to_restaurant": route_activity_to_restaurant,
        "restaurant_to_home": route_restaurant_to_home or route_activity_to_home,
    }

    rejections: list[str] = []

    if total_driving > max_driving:
        rejections.append(
            f"Total driving {total_driving:.0f} min exceeds family limit of {max_driving} min"
        )

    rejections.extend(conflicts)

    if rejections:
        return {
            "current_verdicts": [
                AgentVerdict(
                    agent_name="logistics",
                    verdict="REJECTED",
                    is_hard_constraint=True,
                    confidence=1.0,
                    rejection_reason="; ".join(rejections),
                    recommendation="Search within smaller radius or choose closer activity",
                )
            ],
            "route_data": route_data,
            "negotiation_log": [f"logistics: REJECTED — {'; '.join(rejections)}"],
        }

    return {
        "current_verdicts": [
            AgentVerdict(
                agent_name="logistics",
                verdict="APPROVED",
                is_hard_constraint=True,
                confidence=1.0,
                details={
                    "total_driving_minutes": total_driving,
                    "home_to_activity_minutes": route_home_to_activity.duration_minutes,
                },
            )
        ],
        "route_data": route_data,
        "negotiation_log": [
            f"logistics: APPROVED — {total_driving:.0f} min total driving"
        ],
    }


def _detect_timeline_conflicts(
    state: WeekendPlanState,
    home_to_activity: RouteResult,
    activity_to_restaurant: RouteResult | None,
    restaurant_to_home: RouteResult,
) -> list[str]:
    """
    Detect timeline conflicts in the day plan.

    Returns a list of human-readable conflict strings (empty = no conflicts).
    """
    proposal = state["primary_activity"]
    if proposal is None:
        return []

    conflicts: list[str] = []

    # Check 1: departure before 6am
    departure = proposal.start_time - timedelta(minutes=home_to_activity.duration_minutes)
    if departure.hour < EARLIEST_DEPARTURE_HOUR:
        conflicts.append(
            f"Departure at {departure.strftime('%H:%M')} is before 6:00 AM"
        )

    # Check 2: full day exceeds 12 hours
    activity_duration_min = proposal.estimated_duration_hours * 60
    total_day_min = (
        home_to_activity.duration_minutes
        + activity_duration_min
        + (activity_to_restaurant.duration_minutes if activity_to_restaurant else 0)
        + MEAL_DURATION_MINUTES
        + restaurant_to_home.duration_minutes
    )
    if total_day_min > MAX_ACCEPTABLE_DAY_HOURS * 60:
        conflicts.append(
            f"Full day plan is {total_day_min / 60:.1f} hours — exceeds {MAX_ACCEPTABLE_DAY_HOURS}h limit"
        )

    return conflicts


def _approved_verdict(reason: str) -> dict:
    return {
        "current_verdicts": [
            AgentVerdict(
                agent_name="logistics",
                verdict="APPROVED",
                is_hard_constraint=True,
                confidence=1.0,
                details={"reason": reason},
            )
        ],
        "route_data": None,
        "negotiation_log": [f"logistics: APPROVED — {reason}"],
    }
