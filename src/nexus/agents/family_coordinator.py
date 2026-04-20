"""
Family coordinator review agent — LOCKED LOCAL (ModelRouter enforces).

Tech §5.6:
- Estimate cell coverage via heuristic
- Search nearby places for family alternatives
- LLM JSON output → FamilyPlanVerdict (parsed manually — avoids schema timeout)
- Hard constraint: teen + no cell service → override to REJECTED
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from nexus.agents.error_boundary import agent_error_boundary
from nexus.llm.prompts import FAMILY_REVIEW_PROMPT, INTENT_PARSE_SYSTEM
from nexus.state.graph_state import WeekendPlanState
from nexus.state.schemas import AgentVerdict, FamilyActivity, FamilyPlanVerdict

logger = logging.getLogger(__name__)

TEEN_AGE_MIN = 12
TEEN_AGE_MAX = 17
NEARBY_SEARCH_RADIUS_MILES = 10.0


@agent_error_boundary("family_coordinator", is_hard_constraint=True)
async def family_coordinator_review(state: WeekendPlanState) -> dict:
    """
    Evaluate proposal for family fit using LLM + hard constraint override.

    Returns: current_verdicts, family_activities, negotiation_log
    """
    proposal = state["primary_activity"]
    family_profile = state["family_profile"]  # use dict access for TypedDict

    if proposal is None or family_profile is None:
        return {
            "current_verdicts": [
                AgentVerdict(
                    agent_name="family_coordinator",
                    verdict="APPROVED",
                    is_hard_constraint=True,
                    confidence=1.0,
                    details={"reason": "No proposal or family to evaluate"},
                )
            ],
            "negotiation_log": ["family_coordinator: APPROVED — nothing to evaluate"],
        }

    registry = state["tool_registry"]

    # ── Cell coverage estimate ─────────────────────────────────────────────
    from nexus.tools.providers.coverage import estimate_cell_coverage

    coverage = await estimate_cell_coverage(proposal.location_coordinates, registry.routing)

    # ── Nearby places for family alternatives ─────────────────────────────
    nearby = await registry.places.search_nearby(
        proposal.location_coordinates,
        NEARBY_SEARCH_RADIUS_MILES,
        categories=["parks", "cafes", "museums", "playgrounds"],
    )

    # ── Hard constraint: teen + no cell service ───────────────────────────
    members = getattr(family_profile, "members", [])
    has_teen = any(
        TEEN_AGE_MIN <= getattr(m, "age", 0) <= TEEN_AGE_MAX for m in members
    )
    requires_cell = any(getattr(m, "requires_cell_service", False) for m in members)

    if (has_teen or requires_cell) and not coverage.has_likely_service:
        return {
            "current_verdicts": [
                AgentVerdict(
                    agent_name="family_coordinator",
                    verdict="REJECTED",
                    is_hard_constraint=True,
                    confidence=1.0,
                    rejection_reason="Location has poor cell coverage — required for family member",
                    recommendation="Search for activity closer to road network or urban area",
                )
            ],
            "negotiation_log": [
                "family_coordinator: REJECTED — teen/required member needs cell coverage"
            ],
        }

    # ── LLM evaluation ────────────────────────────────────────────────────
    router = state["model_router"]
    model = router.get_model("family_coordinator")  # ModelRouter enforces local

    family_summary = "\n".join(
        f"- {getattr(m, 'name', 'Member')} (age {getattr(m, 'age', '?')}): "
        f"interests={getattr(m, 'interests', [])}"
        for m in members
    )

    nearby_summary = "\n".join(
        f"- {p.name} ({p.category}, {p.distance_miles:.1f}mi)"
        for p in nearby[:8]
    )

    prompt = FAMILY_REVIEW_PROMPT.format(
        proposal=proposal.model_dump_json(),
        family=family_summary,
        cell_coverage=f"{'Likely available' if coverage.has_likely_service else 'Poor coverage'} "
                      f"({coverage.road_proximity_miles:.1f}mi from nearest road)",
        nearby_activities=nearby_summary or "None found",
    )

    messages = [SystemMessage(content=INTENT_PARSE_SYSTEM), HumanMessage(content=prompt)]
    fast_model = model.bind(format="json")

    # Defaults: approve with low confidence when LLM fails (non-blocking)
    llm_verdict = "APPROVED"
    llm_rejection_reason: str | None = None
    llm_confidence = 0.5
    llm_family_activities: list[FamilyActivity] = []

    try:
        response = await asyncio.wait_for(fast_model.ainvoke(messages), timeout=60.0)
        raw = _extract_json(response.content)
        llm_verdict = raw.get("verdict", "APPROVED")
        llm_rejection_reason = raw.get("rejection_reason") or None
        llm_confidence = float(raw.get("confidence", 0.5))
        for fa in raw.get("family_activities", []):
            try:
                llm_family_activities.append(FamilyActivity.model_validate(fa))
            except Exception:
                pass
    except asyncio.TimeoutError:
        logger.warning("family_coordinator: LLM timed out — auto-approving")
    except Exception as exc:
        logger.warning("family_coordinator: LLM error (%s) — auto-approving", exc)

    result = FamilyPlanVerdict(
        verdict=llm_verdict,
        is_hard_constraint=True,
        rejection_reason=llm_rejection_reason,
        family_activities=llm_family_activities,
        confidence=llm_confidence,
    )
    verdict = result.to_agent_verdict()

    # TODO(P1): per-member activity scoring and full matching (PRD §8.1 F14)
    return {
        "current_verdicts": [verdict],
        "family_activities": llm_family_activities,
        "negotiation_log": [
            f"family_coordinator: {verdict.verdict} — "
            f"{verdict.rejection_reason or 'family plan accommodated'}"
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
