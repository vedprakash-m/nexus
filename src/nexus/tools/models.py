"""
Tool data models — typed results from all external data providers.

Each model includes data_age_minutes and confidence fields for
transparency in the plan output (data confidence labels — UX §6.3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from nexus.state.confidence import DataConfidence

# Type alias for coordinates
Coordinates = tuple[float, float]

# Confidence field shorthand
_ConfidenceVal = Literal["verified", "cached", "estimated"]


class _DataMixin(BaseModel):
    """Fields present on every tool result."""

    data_age_minutes: int = 0
    confidence: _ConfidenceVal = "verified"

    @property
    def data_confidence(self) -> DataConfidence:
        return DataConfidence(self.confidence)


# ─────────────────────────────────────────────────────────────────────────────
# Weather models
# ─────────────────────────────────────────────────────────────────────────────


class AirQuality(_DataMixin):
    """Air quality index data."""

    aqi: int  # AQI >100 triggers meteorology REJECTED


class DaylightWindow(_DataMixin):
    """Sunrise/sunset for the activity date and location."""

    sunrise: datetime
    sunset: datetime  # activity end must be 30min before this


class WeatherForecast(_DataMixin):
    """
    Weather forecast for the activity location and date.

    Required fields (missing any → AttributeError in meteorology agent):
    - precipitation_probability: float  — compared against 40% hard threshold
    - lightning_risk: bool              — checked against has_exposed_sections
    - conditions_text: str              — shown in plan output (human-readable)
    - temperature_high_f: float         — informational

    Compound fields for agent consumption:
    - aqi: AirQuality                   — checked against 100 threshold
    - daylight: DaylightWindow          — sunset buffer check
    """

    precipitation_probability: float  # 0.0–100.0 percent
    lightning_risk: bool
    conditions_text: str
    temperature_high_f: float
    aqi: AirQuality | None = None
    daylight: DaylightWindow | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Activity models
# ─────────────────────────────────────────────────────────────────────────────


class ActivityResult(_DataMixin):
    """A candidate activity from the activity provider."""

    activity_id: str  # objective agent excludes already-proposed IDs by this key
    name: str
    location_coordinates: Coordinates
    activity_type: str
    difficulty: str
    elevation_gain_ft: int = 0
    distance_miles: float = 0.0
    description: str = ""
    tags: list[str] = []


# ─────────────────────────────────────────────────────────────────────────────
# Place models
# ─────────────────────────────────────────────────────────────────────────────


class PlaceResult(_DataMixin):
    """A place result from the places provider (restaurant, cafe, etc.)."""

    place_id: str
    name: str
    location_coordinates: Coordinates
    address: str
    category: str
    distance_miles: float = 0.0
    rating: float | None = None
    price_range: str = "$$"
    cuisine_type: str = ""
    is_open: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Routing models
# ─────────────────────────────────────────────────────────────────────────────


class RouteResult(_DataMixin):
    """A routing result between two coordinates."""

    duration_minutes: float  # logistics agent compares against max_total_driving_minutes
    distance_miles: float
    waypoints: list[Coordinates] = []
    is_estimated: bool = False  # True when using haversine fallback


# ─────────────────────────────────────────────────────────────────────────────
# Coverage model
# ─────────────────────────────────────────────────────────────────────────────


class CoverageEstimate(_DataMixin):
    """Heuristic cell coverage estimate for a location."""

    has_likely_service: bool  # family coordinator checks this against requires_cell_service
    road_proximity_miles: float  # distance to nearest major road
    poor_coverage_percentage: float = 0.0  # % of route waypoints with poor coverage
