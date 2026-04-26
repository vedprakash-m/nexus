"""
Helper functions for WeekendPlanState construction and querying.

These are pure functions — no side effects, no I/O.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import TYPE_CHECKING

from nexus.state.schemas import AgentVerdict, AgentFailureType

if TYPE_CHECKING:
    from nexus.config import NexusConfig
    from nexus.state.graph_state import WeekendPlanState


def build_initial_state(
    user_intent: str,
    config: "NexusConfig",
    target_date: date | None = None,
    request_id: str | None = None,
) -> "WeekendPlanState":
    """
    Construct the initial WeekendPlanState from user intent + loaded config.

    This is a factory function because TypedDict cannot have class methods.
    """
    from nexus.state.schemas import FamilyMember, FamilyProfile, UserProfile

    if target_date is None:
        # Default to next Saturday
        today = date.today()
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        target_date = today + timedelta(days=days_until_saturday)

    # Convert config user/family to proper state schema objects
    user = UserProfile(
        name=config.user.name,
        fitness_level=config.user.fitness_level,  # type: ignore[arg-type]
        dietary_restrictions=config.user.dietary_restrictions,
        protein_target_g=config.user.protein_target_g,
        max_driving_minutes=config.user.max_driving_minutes,
        max_restaurant_radius_miles=config.user.max_restaurant_radius_miles,
        home_coordinates=config.user.home_coordinates,
        preferred_activities=config.user.preferred_activities,
    )

    family = FamilyProfile(
        vehicle_count=config.family.vehicle_count,
        max_total_driving_minutes=config.family.max_total_driving_minutes,
        members=[
            FamilyMember(
                name=m.name,
                age=m.age,
                interests=m.interests,
                comfort_distance_miles=m.comfort_distance_miles,
                requires_cell_service=m.requires_cell_service,
            )
            for m in config.family.members
        ],
    )

    return {  # type: ignore[return-value]
        "request_id": request_id or str(uuid.uuid4()),
        "user_intent": user_intent,
        "target_date": target_date,
        "user_profile": user,
        "family_profile": family,
        "plan_requirements": None,
        "primary_activity": None,
        "family_activities": [],
        "meal_plan": None,
        "proposal_history": [],
        "current_verdicts": [],
        "weather_data": None,
        "route_data": None,
        "safety_data": None,
        "iteration_count": 0,
        "max_iterations": config.planning.max_iterations,
        "current_phase": "drafting",
        "rejection_context": None,
        "pending_constraints": [],
        "negotiation_log": [],
        "human_feedback": None,
        "human_rejection_count": 0,
        "output_html": None,
        "output_markdown": None,
        "backup_activity": None,
        "output_confidence_labels": None,
    }


def all_agents_approved(state: "WeekendPlanState") -> bool:
    """Return True if all required review agents have APPROVED or NEEDS_INFO."""
    verdicts = state.get("current_verdicts", [])
    if not verdicts:
        return False
    required_agents = {"meteorology", "family_coordinator", "nutritional", "logistics"}
    approved_agents = {v.agent_name for v in verdicts if v.verdict in ("APPROVED", "NEEDS_INFO")}
    return required_agents.issubset(approved_agents)


def has_critical_safety_rejection(state: "WeekendPlanState") -> bool:
    """Return True if any hard-constraint agent has a DATA_UNAVAILABLE failure."""
    verdicts = state.get("current_verdicts", [])
    return any(
        v.failure_type == AgentFailureType.DATA_UNAVAILABLE and v.is_hard_constraint
        for v in verdicts
    )


def get_verdict(state: "WeekendPlanState", agent_name: str) -> AgentVerdict | None:
    """Return the most recent verdict from a named agent, or None."""
    verdicts = state.get("current_verdicts", [])
    for v in reversed(verdicts):
        if v.agent_name == agent_name:
            return v
    return None


def compute_tradeoff_summary(state: "WeekendPlanState") -> str:
    """
    Build a human-readable tradeoff summary for the plan template.

    Only called when all agents approved but some were NEEDS_INFO.
    Never includes agent names or technical terms (UX §1.3).
    """
    verdicts = state.get("current_verdicts", [])
    needs_info = [v for v in verdicts if v.verdict == "NEEDS_INFO"]
    if not needs_info:
        return ""

    parts = []
    for v in needs_info:
        if v.recommendation:
            parts.append(v.recommendation)

    return " · ".join(parts) if parts else "Some details couldn't be verified."


def prepare_llm_context(state: "WeekendPlanState") -> dict:
    """
    Produce a slimmed-down state dict safe to include in LLM prompts.

    Context pruning (Tech §6.5):
    - proposal_history: only last 2 proposals (avoid context overflow)
    - negotiation_log: only entries from current iteration (last N entries)
    - Strips heavy data like output_html, output_markdown

    Never include: agent names, confidence scores, iteration numbers.
    """
    history = state.get("proposal_history", [])
    log = state.get("negotiation_log", [])

    # Determine current iteration log entries (last 5 entries per iteration)
    current_log = log[-5:] if log else []

    return {
        "user_intent": state.get("user_intent", ""),
        "target_date": str(state.get("target_date", "")),
        "plan_requirements": (
            state["plan_requirements"].model_dump() if state.get("plan_requirements") else {}
        ),
        "primary_activity": (
            state["primary_activity"].model_dump() if state.get("primary_activity") else None
        ),
        "rejection_context": state.get("rejection_context"),
        "recent_proposals": [p.model_dump() for p in history[-2:]],
        "negotiation_notes": current_log,
    }


def ensure_nexus_dirs(config: "NexusConfig") -> None:
    """Delegate to config module — re-exported here for convenience."""
    from nexus.config import ensure_nexus_dirs as _ensure

    _ensure(config)
