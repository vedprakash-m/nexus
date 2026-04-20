"""
Google Places API (Nearby Search) places provider.

Requires GOOGLE_PLACES_API_KEY in ~/.nexus/.env.
Get a key: https://console.cloud.google.com/ → Enable "Places API" → Create API key.
Google gives $200/month free credit (~2,000 nearby search calls).

Cache: 7 days for restaurant info (menus change weekly).
"""

from __future__ import annotations

import logging

import httpx

from nexus.tools.models import Coordinates, PlaceResult

logger = logging.getLogger(__name__)

PLACES_BASE = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
TIMEOUT = 10.0


class GooglePlaces:
    """
    Restaurant and places provider using Google Places API (Nearby Search).

    Requires GOOGLE_PLACES_API_KEY. Falls back gracefully to empty list on
    auth failure (soft constraint — nutritional agent handles missing data).
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search_restaurants(
        self,
        coordinates: Coordinates,
        radius_miles: float,
        dietary_restrictions: list[str] | None = None,
    ) -> list[PlaceResult]:
        """Search for restaurants near coordinates."""
        lat, lon = coordinates
        radius_meters = min(int(radius_miles * 1609), 50000)  # Google max 50km

        params: dict = {
            "key": self._api_key,
            "location": f"{lat},{lon}",
            "radius": radius_meters,
            "type": "restaurant",
            "rankby": "prominence",
        }

        # Map dietary restrictions to keyword hints (best-effort)
        keyword = _dietary_to_keyword(dietary_restrictions or [])
        if keyword:
            params["keyword"] = keyword

        return await self._search(params)

    async def search_nearby(
        self,
        coordinates: Coordinates,
        radius_miles: float,
        categories: list[str] | None = None,
    ) -> list[PlaceResult]:
        """Search for any place type near coordinates."""
        lat, lon = coordinates
        radius_meters = min(int(radius_miles * 1609), 50000)

        place_type = _categories_to_google_type(categories or [])

        params: dict = {
            "key": self._api_key,
            "location": f"{lat},{lon}",
            "radius": radius_meters,
            "type": place_type,
        }

        return await self._search(params)

    async def _search(self, params: dict) -> list[PlaceResult]:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(PLACES_BASE, params=params)
                if resp.status_code in (401, 403):
                    logger.error("Google Places API auth failed — check GOOGLE_PLACES_API_KEY")
                    return []
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status", "")
                if status in ("REQUEST_DENIED", "INVALID_REQUEST"):
                    logger.error("Google Places error: %s — %s", status, data.get("error_message", ""))
                    return []
                if status == "ZERO_RESULTS":
                    return []
        except httpx.HTTPError as e:
            logger.warning("Google Places API error: %s", e)
            return []

        return _parse_google_results(data.get("results", []))


def _parse_google_results(results: list[dict]) -> list[PlaceResult]:
    parsed = []
    for place in results:
        loc = place.get("geometry", {}).get("location", {})
        lat = loc.get("lat", 0.0)
        lon = loc.get("lng", 0.0)

        types = place.get("types", [])
        # Best human-readable type (skip generic ones)
        _skip = {"point_of_interest", "establishment", "food"}
        category = next((t.replace("_", " ").title() for t in types if t not in _skip), "Restaurant")

        price_map = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
        price = price_map.get(place.get("price_level", 2), "$$")

        is_open = place.get("opening_hours", {}).get("open_now", True)

        parsed.append(
            PlaceResult(
                place_id=place.get("place_id", ""),
                name=place.get("name", ""),
                location_coordinates=(lat, lon),
                address=place.get("vicinity", ""),
                category=category,
                distance_miles=0.0,  # not returned by Nearby Search
                rating=place.get("rating"),
                price_range=price,
                cuisine_type=category,
                is_open=is_open,
                data_age_minutes=0,
                confidence="verified",
            )
        )
    return parsed


def _dietary_to_keyword(restrictions: list[str]) -> str:
    """Map dietary restrictions to a Google Places keyword hint (best-effort)."""
    # Google Places doesn't have category-based dietary filters;
    # keyword search is the closest approximation.
    priority = ["vegan", "vegetarian", "gluten-free", "halal", "kosher"]
    for r in priority:
        if r in [x.lower() for x in restrictions]:
            return r
    return ""


def _categories_to_google_type(categories: list[str]) -> str:
    """Map generic category strings to a Google Places type."""
    mapping: dict[str, str] = {
        "food": "restaurant",
        "parks": "park",
        "arts": "museum",
        "restaurants": "restaurant",
        "cafe": "cafe",
        "bar": "bar",
    }
    for cat in categories:
        if cat.lower() in mapping:
            return mapping[cat.lower()]
    return "restaurant"
