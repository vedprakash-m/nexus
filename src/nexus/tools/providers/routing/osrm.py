"""
OSRM routing provider — free, open-source, no API key required.

Public endpoint: router.project-osrm.org
Fallback: haversine × 1.4 Manhattan factor (DataConfidence.ESTIMATED)

Cache: 24h (routes don't change often, and haversine is deterministic).
"""

from __future__ import annotations

import logging
import math

import httpx

from nexus.tools.models import Coordinates, RouteResult

logger = logging.getLogger(__name__)

OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"
TIMEOUT = 8.0

# Haversine fallback constants
MANHATTAN_FACTOR = 1.4
CITY_SPEED_MPH = 35.0
HIGHWAY_SPEED_MPH = 55.0


class OSRMRouting:
    """
    Routing provider using the free OSRM API.

    Falls back to haversine × Manhattan factor if OSRM times out
    or returns an error. Fallback results are marked is_estimated=True
    and confidence="estimated".
    """

    async def get_route(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> RouteResult:
        """Get driving route between two coordinates."""
        try:
            return await self._osrm_route(origin, destination)
        except (httpx.HTTPError, httpx.TimeoutException, KeyError, IndexError) as e:
            logger.warning("OSRM route failed (%s), using haversine fallback", e)
            return self._haversine_estimate(origin, destination)

    async def nearest_road_distance(
        self,
        coordinates: Coordinates,
    ) -> float:
        """Return estimated distance in miles to the nearest major road."""
        # OSRM nearest endpoint snaps to nearest road
        lat, lon = coordinates
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(
                    f"https://router.project-osrm.org/nearest/v1/driving/{lon},{lat}",
                    params={"number": 1},
                )
                resp.raise_for_status()
                data = resp.json()

            waypoints = data.get("waypoints", [])
            if not waypoints:
                return 0.5  # assume near road if no info

            # OSRM returns distance in meters
            distance_m = waypoints[0].get("distance", 0.0)
            return distance_m / 1609.0
        except (httpx.HTTPError, httpx.TimeoutException, KeyError):
            return 0.5  # default assumption

    async def _osrm_route(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> RouteResult:
        origin_lat, origin_lon = origin
        dest_lat, dest_lon = destination

        url = f"{OSRM_BASE}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                url,
                params={"overview": "false", "steps": "false"},
            )
            resp.raise_for_status()
            data = resp.json()

        route = data["routes"][0]
        duration_seconds = route["duration"]  # seconds
        distance_meters = route["distance"]  # meters

        return RouteResult(
            duration_minutes=duration_seconds / 60.0,
            distance_miles=distance_meters / 1609.0,
            is_estimated=False,
            data_age_minutes=0,
            confidence="verified",
        )

    def _haversine_estimate(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> RouteResult:
        """Estimate route using haversine + Manhattan correction factor."""
        distance_miles = _haversine_miles(origin, destination)
        road_distance_miles = distance_miles * MANHATTAN_FACTOR

        # Blended speed: assume 30% city, 70% highway for most weekend trips
        blended_speed = CITY_SPEED_MPH * 0.3 + HIGHWAY_SPEED_MPH * 0.7
        duration_minutes = (road_distance_miles / blended_speed) * 60.0

        return RouteResult(
            duration_minutes=duration_minutes,
            distance_miles=road_distance_miles,
            is_estimated=True,
            data_age_minutes=0,
            confidence="estimated",
        )


def _haversine_miles(a: Coordinates, b: Coordinates) -> float:
    """Calculate great-circle distance between two coordinate pairs in miles."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(h))

    return c * 3958.8  # Earth radius in miles
