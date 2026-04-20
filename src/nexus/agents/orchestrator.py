"""
Orchestrator agents:
- orchestrator_parse_intent: LLM-powered intent parsing → PlanRequirements
- orchestrator_check_consensus: deterministic consensus gate
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from nexus.agents.error_boundary import agent_error_boundary
from nexus.llm.prompts import INTENT_PARSE_PROMPT, INTENT_PARSE_SYSTEM
from nexus.state.graph_state import WeekendPlanState
from nexus.state.schemas import AgentVerdict, PlanRequirements

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from model output (handles prose wrapping)."""
    # Strip markdown fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Grab the first {...} block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}


def _requirements_from_profile(state: WeekendPlanState, raw: dict) -> PlanRequirements:
    """
    Build PlanRequirements from LLM output + profile defaults.
    Any field that's missing or wrong type is filled from profile.
    Never raises — always returns a usable object.
    """
    user = state.get("user_profile")
    family = state.get("family_profile")

    # Derive sensible defaults from user profile
    intent_lower = state.get("user_intent", "").lower()
    if not raw.get("activity_types"):
        # Simple keyword extraction from intent text
        activity_keywords = {
            "hike": "hiking", "hik": "hiking",
            "bike": "cycling", "cycl": "cycling",
            "swim": "swimming",
            "kayak": "kayaking",
            "camp": "camping",
        }
        inferred = [v for k, v in activity_keywords.items() if k in intent_lower]
        raw["activity_types"] = inferred or (list(user.preferred_activities) if user else ["outdoor"])

    family_has_members = bool(family and family.members)

    def _float(key: str, default: float) -> float:
        try:
            return float(raw.get(key, default))
        except (TypeError, ValueError):
            return default

    def _bool(key: str, default: bool) -> bool:
        v = raw.get(key, default)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return default

    def _int(key: str, default: int) -> int:
        try:
            return int(raw.get(key, default))
        except (TypeError, ValueError):
            return default

    # Driving → radius heuristic: ~1 mile/min driving
    max_drive = user.max_driving_minutes if user else 90
    default_radius = _float("search_radius_miles", max_drive * 0.8)

    req_cell = family_has_members and any(
        getattr(m, "requires_cell_service", False)
        for m in (family.members if family else [])
    )

    return PlanRequirements(
        activity_types=raw.get("activity_types", ["outdoor"]),
        target_date=raw.get("target_date"),  # PlanRequirements accepts None
        max_distance_miles=_float("max_distance_miles", 50.0),
        min_elevation_gain_ft=_int("min_elevation_gain_ft", 0),
        must_have_cell_coverage=_bool("must_have_cell_coverage", req_cell),
        family_friendly=_bool("family_friendly", family_has_members),
        dietary_requirements=raw.get("dietary_requirements") or (
            user.dietary_restrictions if user else []
        ),
        require_cell_coverage=_bool("require_cell_coverage", req_cell),
        max_activity_hours=_float("max_activity_hours", 8.0),
        search_radius_miles=default_radius,
    )


@agent_error_boundary("orchestrator", is_hard_constraint=False)
async def orchestrator_parse_intent(state: WeekendPlanState) -> dict:
    """
    Parse user intent into structured PlanRequirements.

    Uses a plain format=json LLM call (not schema-enforced structured output)
    to avoid slow chain-of-thought reasoning on thinking models like qwen3.
    Falls back to profile-derived defaults if the LLM is slow or returns bad JSON.
    """
    router = state["model_router"]
    model = router.get_model("orchestrator")

    user = state["user_profile"]
    family = state["family_profile"]

    if family and family.members:
        family_lines = [
            f"{m.name} age {m.age}" + (", needs cell" if m.requires_cell_service else "")
            for m in family.members
        ]
        family_summary = ", ".join(family_lines)
    else:
        family_summary = "none"

    prompt_text = INTENT_PARSE_PROMPT.format(
        intent=state["user_intent"],
        fitness_level=user.fitness_level if user else "intermediate",
        dietary_restrictions=", ".join(user.dietary_restrictions) if user else "none",
        preferred_activities=", ".join(user.preferred_activities) if user else "outdoor",
        max_driving_minutes=user.max_driving_minutes if user else 90,
        family_summary=family_summary,
    )

    messages = [SystemMessage(content=INTENT_PARSE_SYSTEM), HumanMessage(content=prompt_text)]

    # Use a model bound with format=json (no JSON-schema enforcement — avoids
    # the slow schema-reasoning path in thinking models like qwen3.x).
    fast_model = model.bind(format="json")

    raw: dict = {}
    try:
        response = await asyncio.wait_for(fast_model.ainvoke(messages), timeout=120.0)
        raw = _extract_json(response.content)
        if raw:
            logger.debug("parse_intent: LLM returned JSON keys: %s", list(raw.keys()))
        else:
            logger.warning("parse_intent: LLM returned no parseable JSON — using profile fallback")
    except asyncio.TimeoutError:
        logger.warning("parse_intent: LLM timed out after 60 s — using profile fallback")
    except Exception as exc:
        logger.warning("parse_intent: LLM error (%s) — using profile fallback", exc)

    plan_requirements = _requirements_from_profile(state, raw)

    return {
        "plan_requirements": plan_requirements,
        "current_phase": "drafting",
        "negotiation_log": [f"orchestrator: Parsed intent — {state['user_intent']!r}"],
    }


async def orchestrator_check_consensus(state: WeekendPlanState) -> dict:
    """
    Deterministic consensus gate — no LLM.

    - Increments iteration_count
    - Checks pending_constraints queue (drains if non-empty → force re-draft)
    - Returns updated iteration_count, current_phase, rejection_context
    """
    iteration_count = state.get("iteration_count", 0) + 1
    verdicts = state.get("current_verdicts", [])

    # Drain pending constraints queue (Tech §8.4 mid-flight injection)
    pending = list(state.get("pending_constraints", []))
    if pending:
        constraint_text = "; ".join(pending)
        return {
            "iteration_count": iteration_count,
            "current_phase": "revising",
            "rejection_context": f"Mid-flight constraint added: {constraint_text}",
            "pending_constraints": [],
            "negotiation_log": [
                f"orchestrator: constraint injected — {constraint_text}"
            ],
        }

    # Build rejection summary for objective agent
    rejections = [v for v in verdicts if v.verdict == "REJECTED"]
    rejection_text: str | None = None
    if rejections:
        parts = [
            f"{v.agent_name}: {v.rejection_reason or 'no reason'}"
            for v in rejections
        ]
        rejection_text = " | ".join(parts)

    from nexus.state.helpers import all_agents_approved

    current_phase = "reviewing"
    if all_agents_approved(state):
        current_phase = "validating"
    elif iteration_count >= state.get("max_iterations", 3):
        current_phase = "validating"
    elif rejections:
        current_phase = "revising"

    return {
        "iteration_count": iteration_count,
        "current_phase": current_phase,
        "rejection_context": rejection_text,
        "negotiation_log": [
            f"orchestrator: consensus check iteration {iteration_count} — "
            f"{len(rejections)} rejection(s)"
        ],
    }
