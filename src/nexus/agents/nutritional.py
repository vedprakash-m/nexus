"""
Nutritional review agent — restaurant search + dietary compliance check.

Tech §5.7:
- Search restaurants near activity endpoint
- No restaurants → hard REJECTED (no LLM)
- LLM JSON output → NutritionalVerdict (parsed manually — avoids schema timeout)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from nexus.agents.error_boundary import agent_error_boundary
from nexus.llm.prompts import INTENT_PARSE_SYSTEM, MENU_ANALYSIS_PROMPT
from nexus.state.graph_state import WeekendPlanState
from nexus.state.schemas import AgentVerdict, NutritionalVerdict, RestaurantRecommendation

logger = logging.getLogger(__name__)

RESTAURANT_SEARCH_RADIUS_MILES = 10.0


@agent_error_boundary("nutritional", is_hard_constraint=True)
async def nutritional_review(state: WeekendPlanState) -> dict:
    """
    Find and evaluate a compliant restaurant option near the activity endpoint.

    Returns: current_verdicts, meal_plan, negotiation_log
    """
    proposal = state["primary_activity"]
    user = state["user_profile"]

    if proposal is None:
        return {
            "current_verdicts": [
                AgentVerdict(
                    agent_name="nutritional",
                    verdict="APPROVED",
                    is_hard_constraint=True,
                    confidence=1.0,
                    details={"reason": "No proposal to evaluate"},
                )
            ],
            "negotiation_log": ["nutritional: APPROVED — no proposal yet"],
        }

    registry = state["tool_registry"]
    dietary_restrictions = getattr(user, "dietary_restrictions", []) if user else []

    from nexus.config import NexusConfig

    _config = state.get("config")
    _restaurant_radius = (
        _config.planning.restaurant_search_radius_miles
        if isinstance(_config, NexusConfig)
        else RESTAURANT_SEARCH_RADIUS_MILES
    )

    # ── Search restaurants near endpoint ──────────────────────────────────
    restaurants = await registry.places.search_restaurants(
        proposal.endpoint_coordinates,
        _restaurant_radius,
        dietary_restrictions=dietary_restrictions,
    )

    # Hard stop: no restaurants at all → reject without LLM call
    if not restaurants:
        return {
            "current_verdicts": [
                AgentVerdict(
                    agent_name="nutritional",
                    verdict="REJECTED",
                    is_hard_constraint=True,
                    confidence=1.0,
                    rejection_reason=f"No restaurants found within {_restaurant_radius:.0f} miles of activity endpoint",
                    recommendation="Choose an activity closer to dining options, or raise restaurant_search_radius_miles in your profile",
                )
            ],
            "negotiation_log": [
                f"nutritional: REJECTED — no restaurants within {_restaurant_radius:.0f} miles"
            ],
        }

    # ── LLM dietary compliance evaluation ─────────────────────────────────
    router = state["model_router"]
    model = router.get_model("nutritional")

    restaurant_summary = "\n".join(
        f"- {r.name} ({r.cuisine_type}, {r.price_range}, "
        f"rating {r.rating or 'N/A'}, {r.distance_miles:.1f}mi): {r.address}"
        for r in restaurants[:10]
    )

    protein_target = getattr(user, "protein_target_g", 0) if user else 0

    prompt = MENU_ANALYSIS_PROMPT.format(
        dietary_restrictions=", ".join(dietary_restrictions) or "none",
        protein_target_g=protein_target,
        restaurants=restaurant_summary,
    )

    messages = [SystemMessage(content=INTENT_PARSE_SYSTEM), HumanMessage(content=prompt)]
    fast_model = model.bind(format="json")

    # Defaults: approve with first restaurant when LLM fails
    llm_verdict = "APPROVED"
    llm_rejection_reason: str | None = None
    llm_confidence = 0.5
    llm_restaurant: RestaurantRecommendation | None = None

    try:
        response = await asyncio.wait_for(fast_model.ainvoke(messages), timeout=120.0)
        raw = _extract_json(response.content)
        llm_verdict = raw.get("verdict", "APPROVED")
        llm_rejection_reason = raw.get("rejection_reason") or None
        llm_confidence = float(raw.get("confidence", 0.5))
        rec = raw.get("recommended_restaurant")
        if rec and isinstance(rec, dict):
            try:
                llm_restaurant = RestaurantRecommendation.model_validate(rec)
            except Exception:
                pass
    except asyncio.TimeoutError:
        logger.warning("nutritional: LLM timed out — auto-approving with first restaurant")
    except Exception as exc:
        logger.warning("nutritional: LLM error (%s) — auto-approving", exc)

    result = NutritionalVerdict(
        verdict=llm_verdict,
        is_hard_constraint=True,
        rejection_reason=llm_rejection_reason,
        recommended_restaurant=llm_restaurant,
        confidence=llm_confidence,
    )
    verdict = result.to_agent_verdict()

    # If LLM failed to pick one, fall back to first search result
    if result.recommended_restaurant is None and restaurants:
        r0 = restaurants[0]
        result = NutritionalVerdict(
            verdict="APPROVED",
            is_hard_constraint=True,
            recommended_restaurant=RestaurantRecommendation(
                name=r0.name,
                cuisine_type=r0.cuisine_type or "restaurant",
                address=r0.address,
                distance_miles=r0.distance_miles,
                dietary_compliant=True,
                price_range=r0.price_range or "$$",
                google_rating=r0.rating,
                coordinates=r0.location_coordinates,
            ),
            confidence=0.4,
        )
        verdict = result.to_agent_verdict()

    # Back-fill coordinates from the matching PlaceResult so logistics_review
    # can route to the restaurant correctly (coordinates are not in LLM output).
    if result.recommended_restaurant:
        rec_name_lower = result.recommended_restaurant.name.lower()
        # Try exact match first, then substring match to handle LLM name drift
        matched = next(
            (r for r in restaurants if r.name.lower() == rec_name_lower),
            None,
        ) or next(
            (
                r
                for r in restaurants
                if r.name.lower() in rec_name_lower or rec_name_lower in r.name.lower()
            ),
            None,
        )
        if matched:
            result.recommended_restaurant.coordinates = matched.location_coordinates
        elif restaurants:
            # LLM hallucinated a name — fall back to first search result
            result.recommended_restaurant.coordinates = restaurants[0].location_coordinates

    # TODO(P1): full macro optimization — protein_target_g matching (PRD §8.1 F13)

    return {
        "current_verdicts": [verdict],
        "meal_plan": result.recommended_restaurant,
        "negotiation_log": [
            f"nutritional: {verdict.verdict} — "
            f"{result.recommended_restaurant.name if result.recommended_restaurant else 'no restaurant selected'}"
        ],
    }


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*?\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}
