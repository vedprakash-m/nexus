"""
Yelp Fusion API places provider.

Requires YELP_API_KEY in ~/.nexus/.env.
Cache: 7 days for restaurant info (menus change weekly).
"""

from __future__ import annotations

import logging

import httpx

from nexus.tools.models import Coordinates, PlaceResult

logger = logging.getLogger(__name__)

YELP_BASE = "https://api.yelp.com/v3"
TIMEOUT = 10.0


class YelpPlaces:
    """
    Restaurant and places provider using Yelp Fusion API.

    Requires YELP_API_KEY. Falls back gracefully to empty list on auth failure
    (soft constraint — nutritional agent handles missing data).
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def search_restaurants(
        self,
        coordinates: Coordinates,
        radius_miles: float,
        dietary_restrictions: list[str] | None = None,
    ) -> list[PlaceResult]:
        """Search for restaurants near coordinates."""
        lat, lon = coordinates
        radius_meters = min(int(radius_miles * 1609), 40000)  # Yelp max 40km

        # Map dietary restrictions to Yelp categories
        categories = _dietary_to_yelp_categories(dietary_restrictions or [])

        params: dict = {
            "latitude": lat,
            "longitude": lon,
            "radius": radius_meters,
            "categories": categories or "restaurants",
            "limit": 20,
            "sort_by": "rating",
        }

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(
                    f"{YELP_BASE}/businesses/search",
                    headers=self._headers,
                    params=params,
                )
                if resp.status_code in (401, 403):
                    logger.error("Yelp API auth failed — check YELP_API_KEY")
                    return []
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.warning("Yelp API error: %s", e)
            return []

        return _parse_yelp_businesses(data.get("businesses", []))

    async def search_nearby(
        self,
        coordinates: Coordinates,
        radius_miles: float,
        categories: list[str] | None = None,
    ) -> list[PlaceResult]:
        """Search for any place type near coordinates."""
        lat, lon = coordinates
        radius_meters = min(int(radius_miles * 1609), 40000)
        yelp_cats = ",".join(categories or ["food", "parks", "arts"])

        params: dict = {
            "latitude": lat,
            "longitude": lon,
            "radius": radius_meters,
            "categories": yelp_cats,
            "limit": 20,
            "sort_by": "rating",
        }

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(
                    f"{YELP_BASE}/businesses/search",
                    headers=self._headers,
                    params=params,
                )
                if resp.status_code in (401, 403):
                    return []
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.warning("Yelp API error: %s", e)
            return []

        return _parse_yelp_businesses(data.get("businesses", []))


def _parse_yelp_businesses(businesses: list[dict]) -> list[PlaceResult]:
    results = []
    for biz in businesses:
        coords = biz.get("coordinates", {})
        lat = coords.get("latitude", 0.0)
        lon = coords.get("longitude", 0.0)

        location = biz.get("location", {})
        address_parts = location.get("display_address", [])
        address = ", ".join(address_parts)

        categories = biz.get("categories", [])
        category = categories[0]["title"] if categories else "Restaurant"

        results.append(
            PlaceResult(
                place_id=biz.get("id", ""),
                name=biz.get("name", ""),
                location_coordinates=(lat, lon),
                address=address,
                category=category,
                distance_miles=biz.get("distance", 0.0) / 1609.0,
                rating=biz.get("rating"),
                price_range=biz.get("price", "$$"),
                cuisine_type=category,
                is_open=not biz.get("is_closed", False),
                data_age_minutes=0,
                confidence="verified",
            )
        )
    return results


def _dietary_to_yelp_categories(restrictions: list[str]) -> str:
    """Map dietary restrictions to Yelp category strings."""
    mapping: dict[str, str] = {
        "vegetarian": "vegetarian",
        "vegan": "vegan",
        "gluten-free": "gluten_free",
        "halal": "halal",
        "kosher": "kosher",
    }
    cats = [mapping[r.lower()] for r in restrictions if r.lower() in mapping]
    return ",".join(cats) if cats else ""
