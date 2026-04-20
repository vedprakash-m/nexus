"""
AgentNode Protocol — shared interface contract for all 10 LangGraph nodes.

Every agent function — LLM or deterministic — must conform to this signature.
Used by pyright --strict for type-checking at task 9.1 wiring time.
"""

from __future__ import annotations

from typing import Protocol

from nexus.state.graph_state import WeekendPlanState


class AgentNode(Protocol):
    """
    Contract for all agent nodes in the LangGraph StateGraph.

    LangGraph Pattern: Every node is a plain async function that receives
    the full state TypedDict and returns a partial dict of updates to merge.
    """

    async def __call__(self, state: WeekendPlanState) -> dict:
        """
        Execute agent logic and return state updates.

        Returns:
            Partial dict with keys matching WeekendPlanState fields.
            Review agents must include an AgentVerdict in current_verdicts.
            Draft agents must include primary_activity and/or plan_requirements.
        """
        ...
