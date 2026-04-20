"""
Save plan agent — terminal node, writes Markdown to ~/.nexus/plans/.

Tech §5.11
"""

from __future__ import annotations

import logging

from nexus.agents.error_boundary import agent_error_boundary
from nexus.output.filenames import plan_filename
from nexus.state.graph_state import WeekendPlanState

logger = logging.getLogger(__name__)


@agent_error_boundary("save_plan", is_hard_constraint=False)
async def save_approved_plan(state: WeekendPlanState) -> dict:
    """
    Write the approved plan's Markdown to ~/.nexus/plans/.

    Returns: current_phase="completed"
    """
    config = state["config"]
    proposal = state["primary_activity"]
    target_date = state["target_date"]
    markdown = state.get("output_markdown")

    if not markdown or proposal is None:
        logger.warning("save_plan: no markdown output to save")
        return {
            "current_phase": "completed",
            "negotiation_log": ["save_plan: no output to save"],
        }

    filename = plan_filename(proposal.activity_name, target_date)
    plans_dir = config.paths.plans_dir
    plans_dir.mkdir(parents=True, exist_ok=True)

    output_path = plans_dir / filename
    output_path.write_text(markdown, encoding="utf-8")
    logger.info("Plan saved to %s", output_path)

    return {
        "current_phase": "completed",
        "negotiation_log": [f"save_plan: saved to {filename}"],
    }
