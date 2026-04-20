"""
Plan synthesizer agent — hybrid deterministic + LLM narrative.

Tech §5.10:
- Slimmed state context via prepare_llm_context()
- LLM generates narrative prose ONLY (no facts/numbers from LLM)
- render_plan_html() and render_plan_markdown() called here
- backup_activity from proposal_history[-2] or generate_relaxed_variant()
"""

from __future__ import annotations

import asyncio
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from nexus.agents.error_boundary import agent_error_boundary
from nexus.llm.prompts import INTENT_PARSE_SYSTEM, PLAN_NARRATION_PROMPT
from nexus.state.graph_state import WeekendPlanState
from nexus.state.schemas import ActivityProposal

logger = logging.getLogger(__name__)


@agent_error_boundary("synthesizer", is_hard_constraint=False)
async def plan_synthesizer(state: WeekendPlanState) -> dict:
    """
    Synthesize the approved plan into output artifacts.

    Returns: output_html, output_markdown, current_phase, backup_activity
    """
    from nexus.output.markdown import render_plan_markdown
    from nexus.state.helpers import prepare_llm_context

    proposal = state["primary_activity"]
    if proposal is None:
        # All planning passes produced no activity — surface a real error instead
        # of silently returning a dict with no output_html, which causes the runner
        # to emit the misleading "Planning completed but produced no output" message.
        from nexus.resilience import HardConstraintDataUnavailable
        raise HardConstraintDataUnavailable(
            "activity_proposal",
            "No suitable activity could be found within your constraints after all planning passes.",
        )

    # ── Slim context for LLM ──────────────────────────────────────────────
    llm_context = prepare_llm_context(state)

    # ── LLM narrative generation ──────────────────────────────────────────
    router = state["model_router"]
    model = router.get_model("synthesizer")

    family_profile = state.get("family_profile")
    family_names = []
    if family_profile and hasattr(family_profile, "members"):
        family_names = [m.name for m in family_profile.members]

    meal_plan = state.get("meal_plan")
    weather = state.get("weather_data")

    prompt = PLAN_NARRATION_PROMPT.format(
        family_names=", ".join(family_names) if family_names else "the family",
        activity_name=proposal.activity_name,
        location_description=f"{proposal.activity_name} area",
        target_date=str(state.get("target_date", "this weekend")),
        conditions_summary=weather.conditions_text if weather else "conditions unknown",
        why_this_plan_context=llm_context.get("rejection_context") or "Best match for your preferences",
        family_activities_summary="\n".join(
            f"- {fa.member_name}: {fa.activity_name}"
            for fa in state.get("family_activities", [])
        ) or "All together",
        restaurant_name=meal_plan.name if meal_plan else "local restaurant",
        cuisine_type=meal_plan.cuisine_type if meal_plan else "",
    )

    messages = [SystemMessage(content=INTENT_PARSE_SYSTEM), HumanMessage(content=prompt)]

    narrative_text = ""
    try:
        narrative_raw = await asyncio.wait_for(model.ainvoke(messages), timeout=60.0)
        # narrative_raw is a string (not structured output)
        narrative_text = narrative_raw.content if hasattr(narrative_raw, "content") else str(narrative_raw)
    except asyncio.TimeoutError:
        logger.warning("synthesizer: LLM timed out — rendering plan without narrative")
    except Exception as exc:
        logger.warning("synthesizer: LLM error (%s) — rendering plan without narrative", exc)

    # ── Render output ─────────────────────────────────────────────────────
    # html.render_plan_html uses Jinja2 plan.html.j2 (full page, Tech §9.4).
    # renderer.render_plan_markdown renders the Markdown artifact only.
    from nexus.output.html import render_plan_html as _render_html_jinja2

    html_output = _render_html_jinja2(state, narrative_text)
    md_output = render_plan_markdown(state, narrative_text)

    # ── Backup activity ───────────────────────────────────────────────────
    proposal_history = state.get("proposal_history", [])
    if len(proposal_history) >= 2:
        backup = proposal_history[-2]  # second-to-last proposal
    else:
        backup = generate_relaxed_variant(state)

    return {
        "output_html": html_output,
        "output_markdown": md_output,
        "current_phase": "human_review",
        "backup_activity": backup,
        "negotiation_log": [f"synthesizer: plan generated for '{proposal.activity_name}'"],
    }


def generate_relaxed_variant(state: WeekendPlanState) -> ActivityProposal | None:
    """
    Generate a relaxed backup activity by widening one soft constraint.

    No LLM call, no tool calls. Pure Python copy with one constraint relaxed.
    Priority: (1) max_distance +5mi, (2) min_elevation -200ft, (3) remove exposed sections.
    """
    proposal = state.get("primary_activity")
    if proposal is None:
        return None

    requirements = state.get("plan_requirements")
    updates: dict = {}

    if requirements:
        if getattr(requirements, "max_distance_miles", 20) < 20:
            updates["max_distance_miles"] = getattr(requirements, "max_distance_miles", 15) + 5
        elif getattr(requirements, "min_elevation_gain_ft", 0) > 500:
            updates["has_exposed_sections"] = False
        else:
            # Widen the activity's search radius so the backup draws from a
            # broader pool — making it genuinely different from the primary.
            updates["search_radius_miles"] = proposal.search_radius_miles + 5.0
            updates["has_exposed_sections"] = False

    updates["activity_name"] = proposal.activity_name + " (Relaxed)"

    return proposal.model_copy(update=updates)
