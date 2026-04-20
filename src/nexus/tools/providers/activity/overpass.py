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
    # ── Issaquah Alps (closest to Sammamish, intermediate/advanced) ───────
    {"name": "West Tiger 3 via West Tiger Railroad Grade", "lat": 47.5166, "lon": -121.9813,
     "type": "hiking", "difficulty": "hard", "miles": 5.4, "elev": 2100,
     "tags": ["summit", "views", "strenuous", "Issaquah-Alps"]},
    {"name": "West Tiger 1 & 2 Loop", "lat": 47.5201, "lon": -121.9743,
     "type": "hiking", "difficulty": "hard", "miles": 9.5, "elev": 2900,
     "tags": ["summit", "views", "strenuous", "Issaquah-Alps", "advanced"]},
    {"name": "East Tiger Mountain Trail", "lat": 47.4930, "lon": -121.9372,
     "type": "hiking", "difficulty": "hard", "miles": 6.6, "elev": 1900,
     "tags": ["summit", "views", "strenuous", "Issaquah-Alps", "advanced", "remote"]},
    {"name": "Squak Mountain State Park — Central Peak Loop", "lat": 47.5194, "lon": -122.0397,
     "type": "hiking", "difficulty": "moderate", "miles": 5.0, "elev": 1200,
     "tags": ["forest", "wildflowers", "quiet", "Issaquah-Alps"]},
    {"name": "Cougar Mountain — Red Town to Wilderness Peak", "lat": 47.5301, "lon": -122.0742,
     "type": "hiking", "difficulty": "moderate", "miles": 7.5, "elev": 1100,
     "tags": ["forest", "nature-reserve", "Issaquah-Alps", "loop"]},
    {"name": "Grand Ridge Park — Grand Ridge Trail", "lat": 47.5932, "lon": -122.0156,
     "type": "hiking", "difficulty": "moderate", "miles": 4.8, "elev": 650,
     "tags": ["forest", "ridge", "views", "Sammamish-adjacent"]},
    # ── Snoqualmie corridor (30–45 min from Sammamish, top hikes) ─────────
    {"name": "Mount Si Trail", "lat": 47.4882, "lon": -121.7254,
     "type": "hiking", "difficulty": "hard", "miles": 8.0, "elev": 3150,
     "tags": ["summit", "views", "strenuous", "iconic", "exposed"]},
    {"name": "Mount Teneriffe via Teneriffe Falls", "lat": 47.4734, "lon": -121.7179,
     "type": "hiking", "difficulty": "hard", "miles": 13.8, "elev": 3800,
     "tags": ["summit", "waterfall", "strenuous", "advanced", "exposed"]},
    {"name": "Little Si Trail", "lat": 47.4897, "lon": -121.7333,
     "type": "hiking", "difficulty": "moderate", "miles": 5.0, "elev": 1200,
     "tags": ["views", "forest", "family-friendly"]},
    {"name": "Rattlesnake Ledge Trail", "lat": 47.4330, "lon": -121.7699,
     "type": "hiking", "difficulty": "moderate", "miles": 4.0, "elev": 1100,
     "tags": ["views", "popular", "exposed"]},
    {"name": "Rattlesnake Mountain Traverse to East Peak", "lat": 47.4283, "lon": -121.7533,
     "type": "hiking", "difficulty": "hard", "miles": 12.0, "elev": 2050,
     "tags": ["summit", "views", "strenuous", "advanced", "exposed"]},
    {"name": "Twin Falls Trail", "lat": 47.4511, "lon": -121.6872,
     "type": "hiking", "difficulty": "moderate", "miles": 2.6, "elev": 500,
     "tags": ["waterfall", "old-growth", "family-friendly"]},
    {"name": "Franklin Falls Trail", "lat": 47.4268, "lon": -121.6261,
     "type": "hiking", "difficulty": "easy", "miles": 2.0, "elev": 400,
     "tags": ["waterfall", "family-friendly"]},
    {"name": "McClellan Butte Trail", "lat": 47.4102, "lon": -121.6503,
     "type": "hiking", "difficulty": "hard", "miles": 10.0, "elev": 3700,
     "tags": ["summit", "views", "strenuous", "advanced", "exposed", "rocky"]},
    {"name": "Mailbox Peak Trail (New Trail)", "lat": 47.4631, "lon": -121.6943,
     "type": "hiking", "difficulty": "hard", "miles": 9.4, "elev": 4000,
     "tags": ["summit", "views", "strenuous", "advanced", "exposed", "iconic"]},
    {"name": "Dirty Harry's Balcony & Peak", "lat": 47.4423, "lon": -121.7096,
     "type": "hiking", "difficulty": "hard", "miles": 8.4, "elev": 2800,
     "tags": ["summit", "views", "strenuous", "advanced", "exposed"]},
    {"name": "Ira Spring Trail to Mason Lake & Mount Defiance", "lat": 47.3842, "lon": -121.6963,
     "type": "hiking", "difficulty": "hard", "miles": 8.0, "elev": 2900,
     "tags": ["summit", "lake", "views", "strenuous", "advanced"]},
    {"name": "Snow Lake Trail", "lat": 47.4463, "lon": -121.4247,
     "type": "hiking", "difficulty": "moderate", "miles": 6.4, "elev": 1800,
     "tags": ["alpine-lake", "views", "popular", "Snoqualmie-Pass"]},
    {"name": "Commonwealth Basin — Red Pass", "lat": 47.4411, "lon": -121.4255,
     "type": "hiking", "difficulty": "hard", "miles": 9.6, "elev": 2950,
     "tags": ["alpine", "views", "strenuous", "Snoqualmie-Pass", "advanced"]},
    {"name": "Kendall Katwalk", "lat": 47.4398, "lon": -121.4142,
     "type": "hiking", "difficulty": "hard", "miles": 10.5, "elev": 2900,
     "tags": ["exposed", "views", "strenuous", "advanced", "Snoqualmie-Pass", "iconic"]},
    {"name": "Granite Mountain Lookout", "lat": 47.3962, "lon": -121.6644,
     "type": "hiking", "difficulty": "hard", "miles": 8.6, "elev": 3800,
     "tags": ["summit", "lookout", "views", "strenuous", "advanced", "exposed"]},
    # ── North Bend / Cedar River Watershed area ───────────────────────────
    {"name": "Lake Serene & Bridal Veil Falls", "lat": 47.7944, "lon": -121.3921,
     "type": "hiking", "difficulty": "hard", "miles": 8.0, "elev": 4200,
     "tags": ["alpine-lake", "waterfall", "strenuous", "advanced", "exposed", "views"]},
    {"name": "Barclay Lake & Stone Lake Loop", "lat": 47.7888, "lon": -121.4559,
     "type": "hiking", "difficulty": "moderate", "miles": 6.0, "elev": 1500,
     "tags": ["alpine-lake", "forest", "views"]},
    # ── Stevens Pass / Skykomish area (within 50 mi) ──────────────────────
    {"name": "Chain Lakes Loop (Mt Baker area)", "lat": 47.8441, "lon": -121.6830,
     "type": "hiking", "difficulty": "moderate", "miles": 6.5, "elev": 1300,
     "tags": ["alpine-lake", "wildflowers", "views"]},
    {"name": "Wallace Falls Trail", "lat": 47.8671, "lon": -121.6800,
     "type": "hiking", "difficulty": "moderate", "miles": 5.6, "elev": 1350,
     "tags": ["waterfall", "forest", "views"]},
    {"name": "Heybrook Lookout", "lat": 47.8354, "lon": -121.5908,
     "type": "hiking", "difficulty": "moderate", "miles": 2.6, "elev": 850,
     "tags": ["lookout", "views", "short", "family-friendly"]},
    # ── Bellevue / Kirkland / Redmond (easy/nearby, lower priority for advanced) ──
    {"name": "Bridle Trails State Park Loop", "lat": 47.6769, "lon": -122.1651,
     "type": "hiking", "difficulty": "easy", "miles": 3.0, "elev": 100,
     "tags": ["family-friendly", "forest", "equestrian"]},
    {"name": "Mercer Slough Nature Park", "lat": 47.5758, "lon": -122.1836,
     "type": "hiking", "difficulty": "easy", "miles": 2.5, "elev": 20,
     "tags": ["wetland", "birdwatching", "accessible", "family-friendly"]},
    {"name": "Marymoor Park Trail", "lat": 47.6674, "lon": -122.1074,
     "type": "hiking", "difficulty": "easy", "miles": 3.0, "elev": 50,
     "tags": ["family-friendly", "lake-view", "accessible", "dog-friendly"]},
    {"name": "Lake Sammamish State Park Loop", "lat": 47.5762, "lon": -122.0659,
     "type": "hiking", "difficulty": "easy", "miles": 2.0, "elev": 50,
     "tags": ["lake", "family-friendly", "beach", "picnic"]},
    # ── Tukwila / Auburn / Federal Way (south) ────────────────────────────
    {"name": "Dash Point State Park", "lat": 47.3243, "lon": -122.4091,
     "type": "hiking", "difficulty": "easy", "miles": 3.5, "elev": 200,
     "tags": ["beach", "forest", "family-friendly"]},
    {"name": "Point Defiance Park Trails", "lat": 47.3113, "lon": -122.5185,
     "type": "hiking", "difficulty": "easy", "miles": 5.0, "elev": 200,
     "tags": ["waterfront", "old-growth", "beach", "family-friendly"]},
]

# Difficulty ordering for filtering (lower = easier)
_DIFFICULTY_ORDER = {"easy": 0, "moderate": 1, "hard": 2}
# Map fitness level → minimum difficulty to include in results
_FITNESS_MIN_DIFFICULTY = {
    "beginner":     "easy",
    "intermediate": "moderate",
    "advanced":     "moderate",   # advanced users can still choose moderate
    "elite":        "hard",
}


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
    fitness_level: str = "intermediate",
) -> list[ActivityResult]:
    """Return curated PNW trails within radius, filtered by activity type and difficulty.

    Results are sorted so harder/more-elevation trails for advanced users come first,
    not just the nearest flat park.
    """
    lat, lon = coordinates
    type_lower = [t.lower() for t in activity_types]

    # Minimum difficulty tier for this fitness level
    min_diff = _FITNESS_MIN_DIFFICULTY.get(fitness_level.lower(), "easy")
    min_tier = _DIFFICULTY_ORDER.get(min_diff, 0)

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

    # Sort: prefer harder trails for advanced users; within same difficulty tier, sort by distance
    def _sort_key(r: ActivityResult) -> tuple[int, float]:
        tier = _DIFFICULTY_ORDER.get(r.difficulty, 0)
        # For advanced/elite: prefer HIGHER difficulty first (invert tier)
        # For beginner: prefer LOWER difficulty (keep tier as-is)
        if min_tier >= 1:
            difficulty_score = -tier  # higher difficulty = lower sort key = first
        else:
            difficulty_score = tier
        dist = _haversine_miles(lat, lon, r.location_coordinates[0], r.location_coordinates[1])
        return (difficulty_score, dist)

    results.sort(key=_sort_key)

    # Filter out trails below minimum difficulty for advanced users (after sorting)
    if min_tier > 0:
        results = [r for r in results if _DIFFICULTY_ORDER.get(r.difficulty, 0) >= min_tier] + \
                  [r for r in results if _DIFFICULTY_ORDER.get(r.difficulty, 0) < min_tier]

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
        fitness_level: str = "intermediate",
    ) -> list[ActivityResult]:
        """Search for activities within radius_miles of coordinates."""
        lat, lon = coordinates
        radius_meters = int(radius_miles * 1609)
        is_hiking = any("hik" in t.lower() or "trail" in t.lower() or "outdoor" in t.lower()
                        for t in activity_types)

        tags = _activity_types_to_tags(activity_types)

        query_parts: list[str] = []

        # For hiking: prioritise named OSM route=hiking relations (real named trail routes)
        if is_hiking:
            query_parts.append(
                f'  relation["route"="hiking"]["name"](around:{radius_meters},{lat},{lon});'
            )
            query_parts.append(
                f'  relation["route"="foot"]["name"](around:{radius_meters},{lat},{lon});'
            )

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

        # Only add generic park catch-all for non-hiking requests
        if not is_hiking:
            query_parts.append(
                f'  way["leisure"~"park|nature_reserve"]["name"](around:{radius_meters},{lat},{lon});'
            )
        else:
            # For hiking: add nature_reserve but not generic parks
            query_parts.append(
                f'  way["leisure"="nature_reserve"]["name"](around:{radius_meters},{lat},{lon});'
            )

        overpass_query = (
            "[out:json][timeout:25];\n(\n"
            + "\n".join(query_parts)
            + "\n);\nout center 30;"
        )

        # Use POST with form-encoded body — required by all Overpass mirrors
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.post(
                        endpoint,
                        data={"data": overpass_query},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results = _parse_overpass_results(data, activity_types, fitness_level)
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
        return _static_fallback(coordinates, radius_miles, activity_types, fitness_level)


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


def _parse_overpass_results(
    data: dict, activity_types: list[str], fitness_level: str = "intermediate"
) -> list[ActivityResult]:
    """Convert Overpass API response to ActivityResult list, ranked by difficulty match."""
    results: list[ActivityResult] = []
    seen_names: set[str] = set()

    # Exclude well-known recreational parks that are NOT hiking destinations
    _EXCLUDE_NAMES = {
        "marymoor park", "lake sammamish state park", "bridle trails state park",
        "mercer slough nature park", "coal creek trail",
    }

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name") or tags.get("official_name") or tags.get("short_name")
        if not name:
            continue
        if name.lower() in _EXCLUDE_NAMES:
            continue
        if name in seen_names:
            continue
        seen_names.add(name)

        if element.get("type") == "node":
            lat = element.get("lat", 0.0)
            lon = element.get("lon", 0.0)
        elif "center" in element:
            lat = element["center"].get("lat", 0.0)
            lon = element["center"].get("lon", 0.0)
        else:
            continue

        raw_dist_km = float(tags.get("distance", 0) or 0)
        raw_dist_miles = raw_dist_km * 0.621371 if raw_dist_km > 0 else 0.0
        elev_gain = 0  # Overpass rarely provides elevation gain

        detected_type = _detect_activity_type(tags, activity_types)
        difficulty = _estimate_difficulty(tags, elev_gain, raw_dist_miles)

        results.append(ActivityResult(
            activity_id=f"osm-{element.get('id', name)}",
            name=name,
            location_coordinates=(lat, lon),
            activity_type=detected_type,
            difficulty=difficulty,
            elevation_gain_ft=elev_gain,
            distance_miles=raw_dist_miles,
            description=tags.get("description", ""),
            tags=list(tags.keys()),
            data_age_minutes=0,
            confidence="verified",
        ))

    # Sort: put difficulty-matching results first
    min_diff = _FITNESS_MIN_DIFFICULTY.get(fitness_level.lower(), "easy")
    min_tier = _DIFFICULTY_ORDER.get(min_diff, 0)

    def _rank(r: ActivityResult) -> int:
        tier = _DIFFICULTY_ORDER.get(r.difficulty, 0)
        if min_tier >= 1:
            return -tier  # prefer harder for intermediate/advanced
        return tier

    results.sort(key=_rank)
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


def _estimate_difficulty(tags: dict, elevation_gain_ft: float = 0, distance_miles: float = 0) -> str:
    """Estimate difficulty from OSM tags with elevation/distance heuristic fallback."""
    sac_scale = tags.get("sac_scale", "")
    if "demanding" in sac_scale or "mountain" in sac_scale:
        return "hard"
    if "hiking" in sac_scale:
        return "moderate"
    # Heuristic: use elevation gain or distance when sac_scale is absent
    if elevation_gain_ft > 2000 or distance_miles > 8:
        return "hard"
    if elevation_gain_ft > 700 or distance_miles > 4:
        return "moderate"
    return "easy"
