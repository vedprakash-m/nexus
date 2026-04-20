"""
Overpass API activity provider — free OSM data, no API key required.

Queries OpenStreetMap for parks, trails, beaches, bike routes, and POIs.
Falls back to a curated static PNW dataset when Overpass is unavailable.
"""

from __future__ import annotations

import logging
import math

import httpx

from nexus.tools.models import ActivityResult, Coordinates

logger = logging.getLogger(__name__)

# Multiple Overpass mirrors — try in order until one succeeds
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
]
TIMEOUT = 20.0

# ─────────────────────────────────────────────────────────────────────────────
# Static fallback dataset — curated PNW trails
# Used when Overpass is unavailable or returns 0 results.
# ─────────────────────────────────────────────────────────────────────────────
_STATIC_PNW_TRAILS: list[dict] = [
    # Issaquah Alps / Sammamish / East King County
    {"name": "Rattlesnake Ledge Trail", "lat": 47.4330, "lon": -121.7699,
     "type": "hiking", "difficulty": "moderate", "miles": 4.0, "elev": 1100,
     "tags": ["family-friendly", "views", "paved-road-access"]},
    {"name": "Twin Falls Trail", "lat": 47.4511, "lon": -121.6872,
     "type": "hiking", "difficulty": "moderate", "miles": 2.6, "elev": 500,
     "tags": ["waterfall", "old-growth", "family-friendly"]},
    {"name": "West Tiger 3 (Tiger Mountain)", "lat": 47.5166, "lon": -121.9813,
     "type": "hiking", "difficulty": "hard", "miles": 5.4, "elev": 2100,
     "tags": ["summit", "views", "strenuous"]},
    {"name": "Cougar Mountain Regional Wildland Park", "lat": 47.5301, "lon": -122.0742,
     "type": "hiking", "difficulty": "easy", "miles": 3.5, "elev": 300,
     "tags": ["family-friendly", "forest", "nature-reserve"]},
    {"name": "Squak Mountain State Park", "lat": 47.5194, "lon": -122.0397,
     "type": "hiking", "difficulty": "moderate", "miles": 5.0, "elev": 1200,
     "tags": ["forest", "wildflowers", "quiet"]},
    {"name": "Lake Sammamish State Park Loop", "lat": 47.5762, "lon": -122.0659,
     "type": "hiking", "difficulty": "easy", "miles": 2.0, "elev": 50,
     "tags": ["lake", "family-friendly", "beach", "picnic"]},
    {"name": "Coal Creek Trail", "lat": 47.5688, "lon": -122.1464,
     "type": "hiking", "difficulty": "easy", "miles": 3.5, "elev": 200,
     "tags": ["family-friendly", "creek", "forest"]},
    {"name": "Grand Ridge Park Trail", "lat": 47.5932, "lon": -122.0156,
     "type": "hiking", "difficulty": "moderate", "miles": 4.8, "elev": 650,
     "tags": ["forest", "ridge", "views"]},
    # Snoqualmie corridor
    {"name": "Mount Si Trail", "lat": 47.4882, "lon": -121.7254,
     "type": "hiking", "difficulty": "hard", "miles": 8.0, "elev": 3150,
     "tags": ["summit", "views", "strenuous", "iconic"]},
    {"name": "Little Si Trail", "lat": 47.4897, "lon": -121.7333,
     "type": "hiking", "difficulty": "moderate", "miles": 5.0, "elev": 1200,
     "tags": ["family-friendly", "views", "forest"]},
    {"name": "Franklin Falls Trail", "lat": 47.4268, "lon": -121.6261,
     "type": "hiking", "difficulty": "easy", "miles": 2.0, "elev": 400,
     "tags": ["waterfall", "family-friendly", "paved"]},
    {"name": "Snoqualmie Falls Trail", "lat": 47.5443, "lon": -121.8374,
     "type": "hiking", "difficulty": "easy", "miles": 1.5, "elev": 300,
     "tags": ["waterfall", "iconic", "family-friendly", "accessible"]},
    # Bellevue / Kirkland / Redmond
    {"name": "Bridle Trails State Park", "lat": 47.6769, "lon": -122.1651,
     "type": "hiking", "difficulty": "easy", "miles": 3.0, "elev": 100,
     "tags": ["family-friendly", "forest", "equestrian"]},
    {"name": "Mercer Slough Nature Park", "lat": 47.5758, "lon": -122.1836,
     "type": "hiking", "difficulty": "easy", "miles": 2.5, "elev": 20,
     "tags": ["wetland", "birdwatching", "accessible", "family-friendly"]},
    {"name": "Marymoor Park Trail", "lat": 47.6674, "lon": -122.1074,
     "type": "hiking", "difficulty": "easy", "miles": 3.0, "elev": 50,
     "tags": ["family-friendly", "lake-view", "accessible", "dog-friendly"]},
    # Beach / waterfront
    {"name": "Dash Point State Park", "lat": 47.3243, "lon": -122.4091,
     "type": "hiking", "difficulty": "easy", "miles": 3.5, "elev": 200,
     "tags": ["beach", "forest", "family-friendly", "campground"]},
    {"name": "Point Defiance Park Trails", "lat": 47.3113, "lon": -122.5185,
     "type": "hiking", "difficulty": "easy", "miles": 5.0, "elev": 200,
     "tags": ["waterfront", "old-growth", "beach", "family-friendly"]},
]


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in miles between two lat/lon points."""
    R = 3958.8
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _static_fallback(
    coordinates: Coordinates,
    radius_miles: float,
    activity_types: list[str],
) -> list[ActivityResult]:
    """Return curated PNW trails within radius, filtered by activity type."""
    lat, lon = coordinates
    type_lower = [t.lower() for t in activity_types]

    results: list[ActivityResult] = []
    for trail in _STATIC_PNW_TRAILS:
        dist = _haversine_miles(lat, lon, trail["lat"], trail["lon"])
        if dist > radius_miles:
            continue
        trail_type = trail["type"]
        if type_lower and not any(
            t in trail_type or trail_type in t or "outdoor" in t or "trail" in t
            for t in type_lower
        ):
            continue
        results.append(ActivityResult(
            activity_id=f"static-{trail['name'].lower().replace(' ', '-')}",
            name=trail["name"],
            location_coordinates=(trail["lat"], trail["lon"]),
            activity_type=trail["type"],
            difficulty=trail["difficulty"],
            elevation_gain_ft=trail["elev"],
            distance_miles=trail["miles"],
            description="",
            tags=trail["tags"],
            data_age_minutes=0,
            confidence="estimated",
        ))

    results.sort(key=lambda r: _haversine_miles(lat, lon, r.location_coordinates[0], r.location_coordinates[1]))
    return results[:20]


class OverpassActivities:
    """
    Activity provider using Overpass API (OpenStreetMap).

    Falls back to a curated PNW static dataset when Overpass is unavailable
    or returns 0 named results.
    """

    async def search_activities(
        self,
        coordinates: Coordinates,
        radius_miles: float,
        activity_types: list[str],
    ) -> list[ActivityResult]:
        """Search for activities within radius_miles of coordinates."""
        lat, lon = coordinates
        radius_meters = int(radius_miles * 1609)

        tags = _activity_types_to_tags(activity_types)

        query_parts: list[str] = []
        for tag_key, tag_val in tags:
            if tag_val:
                query_parts.append(
                    f'  way["{tag_key}"="{tag_val}"]["name"](around:{radius_meters},{lat},{lon});'
                    f'\n  node["{tag_key}"="{tag_val}"]["name"](around:{radius_meters},{lat},{lon});'
                )
            else:
                query_parts.append(
                    f'  way["{tag_key}"]["name"](around:{radius_meters},{lat},{lon});'
                )

        # Always include named parks/reserves as catch-all
        query_parts.append(
            f'  way["leisure"~"park|nature_reserve"]["name"](around:{radius_meters},{lat},{lon});'
        )

        overpass_query = (
            "[out:json][timeout:25];\n(\n"
            + "\n".join(query_parts)
            + "\n);\nout center 30;"
        )

        # Use GET (avoids 406 from POST Content-Type conflicts); try each mirror
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.get(endpoint, params={"data": overpass_query})
                    if resp.status_code == 200:
                        data = resp.json()
                        results = _parse_overpass_results(data, activity_types)
                        if results:
                            logger.debug("Overpass: %d results from %s", len(results), endpoint)
                            return results
                        logger.debug("Overpass: 0 named results from %s", endpoint)
                    else:
                        logger.warning("Overpass %s -> HTTP %d", endpoint, resp.status_code)
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.warning("Overpass %s failed: %s", endpoint, e)

        # All endpoints failed or returned empty — use static fallback
        logger.warning("Overpass unavailable — using static PNW fallback dataset")
        return _static_fallback(coordinates, radius_miles, activity_types)


def _activity_types_to_tags(activity_types: list[str]) -> list[tuple[str, str]]:
    """Map activity type strings to OSM tags."""
    mapping: dict[str, list[tuple[str, str]]] = {
        "hiking": [
            ("highway", "path"),
            ("highway", "footway"),
            ("leisure", "nature_reserve"),
            ("natural", "peak"),
        ],
        "cycling": [("highway", "cycleway"), ("route", "bicycle")],
        "biking":  [("highway", "cycleway"), ("route", "bicycle")],
        "beach":   [("natural", "beach"), ("leisure", "beach_resort")],
        "park":    [("leisure", "park"), ("leisure", "recreation_ground")],
        "trail":   [("highway", "path"), ("highway", "footway")],
        "outdoor": [("leisure", "nature_reserve"), ("highway", "path"), ("natural", "peak")],
    }

    tags: list[tuple[str, str]] = []
    for activity_type in activity_types:
        al = activity_type.lower()
        matched = False
        for key, vals in mapping.items():
            if key in al:
                tags.extend(vals)
                matched = True
        if not matched:
            tags.extend(mapping["outdoor"])

    return list(dict.fromkeys(tags or mapping["outdoor"]))


def _parse_overpass_results(data: dict, activity_types: list[str]) -> list[ActivityResult]:
    """Convert Overpass API response to ActivityResult list."""
    results: list[ActivityResult] = []
    seen_ids: set[str] = set()

    for element in data.get("elements", []):
        elem_id = str(element.get("id", ""))
        if elem_id in seen_ids:
            continue
        seen_ids.add(elem_id)

        tags = element.get("tags", {})
        name = tags.get("name") or tags.get("official_name") or tags.get("short_name")
        if not name:
            continue

        if element.get("type") == "node":
            lat = element.get("lat", 0.0)
            lon = element.get("lon", 0.0)
        elif "center" in element:
            lat = element["center"].get("lat", 0.0)
            lon = element["center"].get("lon", 0.0)
        else:
            continue

        detected_type = _detect_activity_type(tags, activity_types)
        difficulty = _estimate_difficulty(tags)

        results.append(ActivityResult(
            activity_id=f"osm-{elem_id}",
            name=name,
            location_coordinates=(lat, lon),
            activity_type=detected_type,
            difficulty=difficulty,
            elevation_gain_ft=0,
            distance_miles=float(tags.get("distance", 0) or 0),
            description=tags.get("description", ""),
            tags=list(tags.keys()),
            data_age_minutes=0,
            confidence="verified",
        ))

    return results[:20]


def _detect_activity_type(tags: dict, requested_types: list[str]) -> str:
    if tags.get("route") == "hiking" or tags.get("highway") in ("footway", "path"):
        return "hiking"
    if tags.get("route") == "bicycle" or tags.get("highway") == "cycleway":
        return "biking"
    if tags.get("natural") == "beach":
        return "beach"
    if tags.get("leisure") == "park":
        return "park"
    return requested_types[0] if requested_types else "outdoor"


def _estimate_difficulty(tags: dict) -> str:
    sac_scale = tags.get("sac_scale", "")
    if "demanding" in sac_scale or "mountain" in sac_scale:
        return "hard"
    if "hiking" in sac_scale:
        return "moderate"
    return "easy"
