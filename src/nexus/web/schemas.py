"""
API request/response Pydantic models — Tech §9.5.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    """Request body for POST /api/plans."""

    intent: str = Field(..., min_length=1, max_length=500)
    target_date: str | None = None  # ISO date string, e.g. "2026-04-19"


class RejectRequest(BaseModel):
    """Request body for POST /api/plans/{id}/reject."""

    reason: str = Field(..., min_length=1, max_length=1000)
    force: bool = False  # If True, bypass repeated-feedback detection and always replan


class ConstraintRequest(BaseModel):
    """Request body for POST /api/plans/{id}/constraint."""

    constraint: str = Field(..., min_length=1, max_length=500)


class FeedbackRequest(BaseModel):
    """Request body for POST /api/plans/{id}/feedback."""

    feedback: str = Field(..., min_length=1, max_length=2000)


class SetupRequest(BaseModel):
    """Request body for POST /api/setup — saves profile YAML."""

    name: str
    home_address: str  # geocoded server-side to home_lat/home_lon via Google Geocoding API
    fitness_level: str
    dietary_restrictions: list[str] = []
    preferred_activities: list[str] = []
    max_driving_minutes: int = 90
    # Planning knobs
    max_iterations: int = 3
    precipitation_threshold_pct: int = 40
    aqi_threshold: int = 100
    min_sunset_buffer_minutes: int = 30
    cell_coverage_road_proximity_miles: float = 1.0
    require_teen_cell_service: bool = False
    earliest_departure_hour: int = 6
    max_day_hours: float = 12.0
    restaurant_search_radius_miles: float = 10.0
    marginal_weather_precip_pct: int = 30
    hospital_search_radius_miles: float = 30.0
    max_candidate_activities: int = 20
    include_meal: bool = True


class ApiKeyRequest(BaseModel):
    """Request body for POST /api/setup/api-keys."""

    google_places_api_key: str | None = None


class PlanResponse(BaseModel):
    """Response for POST /api/plans — returns request_id for WebSocket subscription."""

    request_id: str
    message: str = "Planning started"


class ApproveResponse(BaseModel):
    """Response for POST /api/plans/{id}/approve."""

    request_id: str
    status: str = "approved"
    plan_file: str | None = None


class ApiKeyStatus(BaseModel):
    """Response for GET /api/setup/api-keys/status."""

    places_configured: bool
    places_key_prefix: str | None = None  # First 4 chars only


class PreflightStatus(BaseModel):
    """Response for GET /api/preflight."""

    ollama_running: bool
    model_available: bool
    profile_exists: bool
    all_ok: bool
    issues: list[str] = []
