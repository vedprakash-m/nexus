"""
Protocol interfaces for all tool providers.

Every provider must implement the relevant Protocol to satisfy runtime_checkable.
Pyright --strict catches Protocol violations at type-check time.

Note: estimate_cell_coverage() is NOT defined here — it lives in
tools/providers/coverage.py (task 3.12). This file defines Protocol contracts only.
# estimate_cell_coverage() implemented in tools/providers/coverage.py
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from nexus.tools.models import (
    ActivityResult,
    AirQuality,
    Coordinates,
    DaylightWindow,
    PlaceResult,
    RouteResult,
    WeatherForecast,
)


@runtime_checkable
class WeatherTool(Protocol):
    """Interface for weather data providers."""

    async def get_forecast(
        self,
        coordinates: Coordinates,
        date: datetime,
    ) -> WeatherForecast: ...

    async def get_air_quality(
        self,
        coordinates: Coordinates,
    ) -> AirQuality: ...

    async def get_daylight_window(
        self,
        coordinates: Coordinates,
        date: date,
    ) -> DaylightWindow: ...


@runtime_checkable
class ActivityTool(Protocol):
    """Interface for activity/trail data providers."""

    async def search_activities(
        self,
        coordinates: Coordinates,
        radius_miles: float,
        activity_types: list[str],
    ) -> list[ActivityResult]: ...


@runtime_checkable
class PlacesTool(Protocol):
    """Interface for places/restaurant providers."""

    async def search_restaurants(
        self,
        coordinates: Coordinates,
        radius_miles: float,
        dietary_restrictions: list[str] | None = None,
    ) -> list[PlaceResult]: ...

    async def search_nearby(
        self,
        coordinates: Coordinates,
        radius_miles: float,
        categories: list[str] | None = None,
    ) -> list[PlaceResult]: ...


@runtime_checkable
class RoutingTool(Protocol):
    """Interface for routing/navigation providers."""

    async def get_route(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> RouteResult: ...

    async def nearest_road_distance(
        self,
        coordinates: Coordinates,
    ) -> float:
        """Return distance in miles to the nearest major road."""
        ...
