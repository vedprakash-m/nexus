"""
Objective agent — activity proposal drafter.

Tech §5.4:
1. Programmatic pre-LLM adjustments based on rejection context
2. Fetch activity candidates from tool registry
3. LLM selects best candidate index (tiny JSON); proposal built from candidate data
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage

from nexus.agents.error_boundary import agent_error_boundary
from nexus.llm.prompts import ACTIVITY_RANKING_PROMPT, INTENT_PARSE_SYSTEM
from nexus.state.graph_state import WeekendPlanState
from nexus.state.schemas import ActivityProposal, PlanRequirements
from nexus.tools.models import ActivityResult

logger = logging.getLogger(__name__)


def _candidate_to_proposal(
    candidate: ActivityResult,
    requirements: PlanRequirements,
    start_hour: int = 9,
) -> ActivityProposal:
    """Build an ActivityProposal from a real ActivityResult candidate."""
    # Infer start datetime: use requirements.target_date or today + 1 day
    from datetime import date, timedelta as td

    target = requirements.target_date or (date.today() + td(days=1))
    start_dt = datetime(target.year, target.month, target.day, max(6, min(22, start_hour)), 0)

    coords = candidate.location_coordinates
    duration = min(requirements.max_activity_hours, max(1.0, candidate.distance_miles / 2.5))

    return ActivityProposal(
        activity_name=candidate.name,
        activity_type=candidate.activity_type,
        location_coordinates=coords,
        endpoint_coordinates=coords,  # trailhead = endpoint (out-and-back default)
        route_waypoints=[],
        start_time=start_dt,
        estimated_duration_hours=duration,
        estimated_return_after_sunset=False,
        has_exposed_sections="exposed" in candidate.tags or "summit" in candidate.tags,
        difficulty=candidate.difficulty,
        max_distance_miles=candidate.distance_miles or requirements.max_distance_miles,
        min_elevation_ft=candidate.elevation_gain_ft,
        search_radius_miles=requirements.search_radius_miles,
        require_cell_coverage=requirements.require_cell_coverage,
        max_activity_hours=requirements.max_activity_hours,
    )


@agent_error_boundary("objective", is_hard_constraint=False)
async def objective_draft_proposal(state: WeekendPlanState) -> dict:
    """
    Draft an activity proposal using LLM selection from tool-fetched candidates.

    The LLM returns only a tiny JSON {"choice_index": N, "start_hour": H}.
    The ActivityProposal is built from real candidate data — no LLM-generated
    coordinates or timestamps, which avoids slow schema-enforcement on thinking models.
    Falls back to candidates[0] if the LLM is slow or returns bad JSON.

    Returns: primary_activity, proposal_history, current_phase, negotiation_log
    """
    requirements = state.get("plan_requirements")
    if requirements is None:
        from nexus.resilience import HardConstraintDataUnavailable
        raise HardConstraintDataUnavailable(
            "intent_parsing",
            "Could not understand your request — the local model timed out or failed. "
            "Please try again, or check /preflight to verify Ollama is healthy.",
        )

    user = state["user_profile"]
    rejection_context = state.get("rejection_context") or ""

    # ── Pre-LLM programmatic adjustments (Tech §4.4) ──────────────────────
    requirements = _apply_revision_adjustments(requirements, rejection_context, state)

    state_date_update: dict = {}
    if (
        requirements.target_date is not None
        and requirements.target_date != state.get("target_date")
    ):
        state_date_update["target_date"] = requirements.target_date

    # ── Fetch activity candidates ──────────────────────────────────────────
    registry = state["tool_registry"]
    home = user.home_coordinates if user else (37.7749, -122.4194)

    candidates = await registry.activity.search_activities(
        home,
        requirements.search_radius_miles,
        requirements.activity_types,
    )

    proposal_history = state.get("proposal_history", [])
    proposed_names = {p.activity_name for p in proposal_history}
    candidates = [c for c in candidates if c.name not in proposed_names]

    if not candidates:
        from nexus.resilience import HardConstraintDataUnavailable
        raise HardConstraintDataUnavailable(
            "activity_search",
            f"No activities found near your location within "
            f"{requirements.search_radius_miles:.0f} miles. "
            f"Try a different activity type or increase your driving radius.",
        )

    # ── LLM selection (index only — not full schema) ───────────────────────
    router = state["model_router"]
    model = router.get_model("objective")

    candidates_text = "\n".join(
        f"{i}: {c.name} | {c.activity_type} | {c.difficulty} | {c.distance_miles:.1f}mi"
        for i, c in enumerate(candidates[:12])
    )
    previous_proposals = [p.activity_name for p in proposal_history]

    prompt_text = ACTIVITY_RANKING_PROMPT.format(
        requirements=f"activity={requirements.activity_types}, "
                     f"family_friendly={requirements.family_friendly}, "
                     f"max_hrs={requirements.max_activity_hours}, "
                     f"cell={requirements.require_cell_coverage}",
        candidates=candidates_text,
        rejection_history=rejection_context or "None",
        previous_proposals=", ".join(previous_proposals) if previous_proposals else "None",
    )

    messages = [SystemMessage(content=INTENT_PARSE_SYSTEM), HumanMessage(content=prompt_text)]
    fast_model = model.bind(format="json")

    choice_index = 0
    start_hour = 9
    try:
        response = await asyncio.wait_for(fast_model.ainvoke(messages), timeout=60.0)
        raw = _extract_json_obj(response.content)
        idx = int(raw.get("choice_index", 0))
        if 0 <= idx < len(candidates):
            choice_index = idx
        start_hour = int(raw.get("start_hour", 9))
    except asyncio.TimeoutError:
        logger.warning("objective: LLM timed out — using candidates[0]")
    except Exception as exc:
        logger.warning("objective: LLM error (%s) — using candidates[0]", exc)

    chosen = candidates[choice_index]
    proposal = _candidate_to_proposal(chosen, requirements, start_hour)

    return {
        "primary_activity": proposal,
        "proposal_history": [proposal],
        "current_phase": "reviewing",
        "negotiation_log": [
            f"objective: drafted '{proposal.activity_name}' "
            f"(attempt {len(proposal_history) + 1})"
        ],
        **state_date_update,
    }


def _extract_json_obj(text: str) -> dict:
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


def _apply_revision_adjustments(
    requirements: PlanRequirements,
    rejection_context: str,
    state: WeekendPlanState,
) -> PlanRequirements:
    """
    Programmatic pre-LLM adjustments based on rejection reason.

    These are Python code mutations — not LLM instructions.
    """
    updates: dict = {}

    if "logistics" in rejection_context.lower() and "radius" in rejection_context.lower():
        updates["search_radius_miles"] = requirements.search_radius_miles * 0.8
        logger.debug("Logistics rejection: shrinking radius to %.1f mi", updates["search_radius_miles"])

    if "cell" in rejection_context.lower() or "coverage" in rejection_context.lower():
        updates["require_cell_coverage"] = True
        logger.debug("Cell coverage rejection: requiring cell coverage")

    if "timeline" in rejection_context.lower() or "time" in rejection_context.lower():
        updates["max_activity_hours"] = requirements.max_activity_hours - 0.5
        logger.debug("Timeline rejection: compressing window to %.1fh", updates.get("max_activity_hours", 0))

    if "date" in rejection_context.lower() and "meteorology" in rejection_context.lower():
        from datetime import date
        current_date = state.get("target_date", date.today())
        new_date = current_date + timedelta(days=1)
        logger.debug("Meteorology date rejection: shifting to %s", new_date)
        updates["target_date"] = new_date

    if updates:
        return requirements.model_copy(update=updates)
    return requirements
