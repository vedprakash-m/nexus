"""
All Pydantic data models for the Nexus planning system.

These models serve two purposes:
1. State payloads stored in WeekendPlanState (TypedDict)
2. Structured output targets for LLM agents via .with_structured_output()

Import order: schemas.py imports only stdlib + pydantic. No nexus imports.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from nexus.resilience import AgentFailureType


# ─────────────────────────────────────────────────────────────────────────────
# User & Family Models
# ─────────────────────────────────────────────────────────────────────────────


class FamilyMember(BaseModel):
    """Individual family member profile."""

    name: str
    age: int
    interests: list[str] = Field(default_factory=list)
    comfort_distance_miles: float = 5.0
    requires_cell_service: bool = False


class UserProfile(BaseModel):
    """Primary user's profile — fitness, diet, and location preferences."""

    name: str = "Alex"
    fitness_level: Literal["beginner", "intermediate", "advanced", "elite"] = "intermediate"
    dietary_restrictions: list[str] = Field(default_factory=list)
    protein_target_g: int = 30
    max_driving_minutes: int = 90
    max_restaurant_radius_miles: float = 10.0
    home_coordinates: tuple[float, float] = (37.7749, -122.4194)
    preferred_activities: list[str] = Field(default_factory=list)


class FamilyProfile(BaseModel):
    """Whole-family logistics constraints."""

    vehicle_count: int = 1
    max_total_driving_minutes: int = 180
    members: list[FamilyMember] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Planning Requirement & Activity Models
# ─────────────────────────────────────────────────────────────────────────────


class PlanRequirements(BaseModel):
    """
    Extracted planning constraints from the user's intent.

    Produced by orchestrator_parse_intent() via structured LLM output.
    Mutated (via model_copy) by objective_draft_proposal() revisions.
    """

    activity_types: list[str] = Field(default_factory=list)
    target_date: date | None = None
    max_distance_miles: float = 50.0
    min_elevation_gain_ft: int = 0
    must_have_cell_coverage: bool = False
    family_friendly: bool = True
    dietary_requirements: list[str] = Field(default_factory=list)
    include_meal: bool = True  # False → skip restaurant search (e.g. packed lunch, all-day hike)
    # Mutated fields (revision strategy matrix — Tech §4.4):
    require_cell_coverage: bool = False  # set True on family no-cell rejection
    max_activity_hours: float = 8.0  # reduced by 0.5 on logistics timeline conflict
    search_radius_miles: float = 50.0  # multiplied by 0.8 on logistics rejection


class FamilyActivity(BaseModel):
    """A planned activity for one or more family members."""

    member_name: str
    activity_name: str
    activity_type: str
    location_name: str
    start_time: datetime | None = None
    duration_hours: float = 2.0
    notes: str = ""


class RestaurantRecommendation(BaseModel):
    """A restaurant recommendation for the meal plan."""

    name: str
    cuisine_type: str
    address: str
    distance_miles: float
    dietary_compliant: bool
    price_range: str = "$$"
    google_rating: float | None = None
    notes: str = ""
    coordinates: tuple[float, float] = (0.0, 0.0)  # Populated from PlaceResult after LLM selection


class ActivityProposal(BaseModel):
    """
    A proposed primary activity for the weekend plan.

    Produced by objective_draft_proposal() and reviewed by specialist agents.
    All revision adjustments use model_copy(update={...}) — never mutate in place.
    """

    activity_name: str
    activity_type: str
    location_coordinates: tuple[float, float]
    endpoint_coordinates: tuple[float, float]
    route_waypoints: list[tuple[float, float]] = Field(default_factory=list)
    start_time: datetime
    estimated_duration_hours: float
    estimated_return_after_sunset: bool = False
    has_exposed_sections: bool = False
    difficulty: str = "moderate"
    max_distance_miles: float = 10.0
    min_elevation_ft: int = 0
    # Mutation targets (revision strategy):
    search_radius_miles: float = 50.0
    require_cell_coverage: bool = False
    max_activity_hours: float = 8.0


# ─────────────────────────────────────────────────────────────────────────────
# Verdict Models
# ─────────────────────────────────────────────────────────────────────────────


class AgentVerdict(BaseModel):
    """
    Standard verdict produced by every review agent.

    For deterministic agents: confidence=1.0 always.
    For LLM agents: confidence=0.0–1.0 from model.
    The confidence field is internal — never shown to user (UX §1.3).
    """

    agent_name: str
    verdict: Literal["APPROVED", "REJECTED", "NEEDS_INFO"]
    is_hard_constraint: bool
    confidence: float = 1.0  # always 1.0 for deterministic agents
    rejection_reason: str | None = None
    recommendation: str | None = None  # feeds revision strategy, not shown to user
    details: dict = Field(default_factory=dict)
    failure_type: AgentFailureType | None = None


class FamilyPlanVerdict(BaseModel):
    """
    Structured LLM output from family_coordinator_review().

    Used as the .with_structured_output() target so the LLM
    produces a validated JSON object, not free-form text.
    """

    verdict: Literal["APPROVED", "REJECTED", "NEEDS_INFO"]
    is_hard_constraint: bool = True
    rejection_reason: str | None = None
    family_activities: list[FamilyActivity] = Field(default_factory=list)
    confidence: float = 0.8

    def to_agent_verdict(self) -> AgentVerdict:
        """Convert to the standard AgentVerdict consumed by reducers."""
        return AgentVerdict(
            agent_name="family_coordinator",
            verdict=self.verdict,
            is_hard_constraint=self.is_hard_constraint,
            confidence=self.confidence,
            rejection_reason=self.rejection_reason,
        )


class NutritionalVerdict(BaseModel):
    """
    Structured LLM output from nutritional_review().

    Used as the .with_structured_output() target.
    """

    verdict: Literal["APPROVED", "REJECTED", "NEEDS_INFO"]
    is_hard_constraint: bool = True
    rejection_reason: str | None = None
    recommended_restaurant: RestaurantRecommendation | None = None
    confidence: float = 0.8

    def to_agent_verdict(self) -> AgentVerdict:
        """Convert to the standard AgentVerdict consumed by reducers."""
        return AgentVerdict(
            agent_name="nutritional",
            verdict=self.verdict,
            is_hard_constraint=self.is_hard_constraint,
            confidence=self.confidence,
            rejection_reason=self.rejection_reason,
        )
