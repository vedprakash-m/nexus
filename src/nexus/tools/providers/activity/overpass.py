"""
Overpass API activity provider — free OSM data, no API key required.

Queries OpenStreetMap for parks, trails, beaches, bike routes, and POIs.
Falls back to a curated static PNW dataset when Overpass is unavailable.
"""

from __future__ import annotations

import logging
import math
from typing import Literal

import httpx
from diskcache import Cache

from nexus.tools.models import ActivityResult, Coordinates

logger = logging.getLogger(__name__)

# Multiple Overpass mirrors — try in order until one succeeds
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
]
TIMEOUT = 8.0  # reduced from 20.0 — ISSUE-03; 8s is well above median Overpass latency

# ─────────────────────────────────────────────────────────────────────────────
# Cache keys — ISSUE-05
# ─────────────────────────────────────────────────────────────────────────────
_OVERPASS_COOLDOWN_KEY = "overpass:cooldown"
_OVERPASS_FAIL_COUNT_KEY = "overpass:fail_count"
_CIRCUIT_BREAKER_THRESHOLD = 3   # consecutive failures before cooldown
_CIRCUIT_BREAKER_WINDOW_S = 120  # rolling window TTL for fail counter (seconds)
_CIRCUIT_BREAKER_COOLDOWN_S = 600  # 10-minute cooldown after threshold reached

# ─────────────────────────────────────────────────────────────────────────────
# Geographic bounding — ISSUE-01
# ─────────────────────────────────────────────────────────────────────────────
_PNW_BOUNDS = {"lat_min": 42.0, "lat_max": 50.5, "lon_min": -125.0, "lon_max": -116.0}


def _is_in_pnw(lat: float, lon: float) -> bool:
    return (
        _PNW_BOUNDS["lat_min"] <= lat <= _PNW_BOUNDS["lat_max"]
        and _PNW_BOUNDS["lon_min"] <= lon <= _PNW_BOUNDS["lon_max"]
    )


# Generic activity template types used for non-PNW users (no fixed coordinates)
_GENERIC_TEMPLATES = [
    {"name_tmpl": "[Estimated] Local Hiking Trail", "type": "hiking", "difficulty": "moderate", "miles": 5.0, "elev": 800, "tags": ["estimated", "trail", "outdoor"], "dlat": 0.05, "dlon": -0.03},
    {"name_tmpl": "[Estimated] Scenic Overlook Trail", "type": "hiking", "difficulty": "moderate", "miles": 3.5, "elev": 600, "tags": ["estimated", "views", "outdoor"], "dlat": -0.04, "dlon": 0.06},
    {"name_tmpl": "[Estimated] Nearby State Park", "type": "hiking", "difficulty": "easy", "miles": 2.5, "elev": 200, "tags": ["estimated", "park", "family-friendly"], "dlat": 0.02, "dlon": 0.04},
    {"name_tmpl": "[Estimated] Local Cycling Route", "type": "cycling", "difficulty": "moderate", "miles": 15.0, "elev": 300, "tags": ["estimated", "cycling", "bike"], "dlat": -0.06, "dlon": -0.05},
    {"name_tmpl": "[Estimated] Waterfront Bike Path", "type": "cycling", "difficulty": "easy", "miles": 10.0, "elev": 100, "tags": ["estimated", "cycling", "waterfront"], "dlat": 0.07, "dlon": 0.02},
    {"name_tmpl": "[Estimated] Community Recreation Area", "type": "outdoor", "difficulty": "easy", "miles": 2.0, "elev": 50, "tags": ["estimated", "outdoor", "family-friendly"], "dlat": -0.02, "dlon": -0.07},
    {"name_tmpl": "[Estimated] Local Nature Reserve", "type": "hiking", "difficulty": "easy", "miles": 3.0, "elev": 300, "tags": ["estimated", "nature", "wildlife"], "dlat": 0.08, "dlon": -0.01},
    {"name_tmpl": "[Estimated] Lakeside Trail", "type": "hiking", "difficulty": "moderate", "miles": 4.0, "elev": 400, "tags": ["estimated", "lake", "trail"], "dlat": -0.03, "dlon": 0.08},
]


def _generic_fallback(
    coordinates: Coordinates,
    radius_miles: float,
    activity_types: list[str],
    fitness_level: str,
) -> list[ActivityResult]:
    """Return generic template activities offset from home_coordinates for non-PNW users."""
    lat, lon = coordinates
    type_lower = {t.lower() for t in activity_types}
    results: list[ActivityResult] = []
    for tmpl in _GENERIC_TEMPLATES:
        # Filter by requested type (broad match)
        if type_lower and not any(
            tmpl["type"] in t or t in tmpl["type"] for t in type_lower
        ):
            continue
        a_lat = lat + tmpl["dlat"]
        a_lon = lon + tmpl["dlon"]
        results.append(ActivityResult(
            activity_id=f"template-{tmpl['name_tmpl'].lower().replace(' ', '-').replace('[', '').replace(']', '')}",
            name=tmpl["name_tmpl"],
            location_coordinates=(a_lat, a_lon),
            activity_type=tmpl["type"],
            difficulty=tmpl["difficulty"],
            elevation_gain_ft=tmpl["elev"],
            distance_miles=tmpl["miles"],
            description=f"Estimated location — verify before visiting",
            tags=tmpl["tags"],
            data_age_minutes=0,
            confidence="estimated",
        ))
    # If no type match, return all templates
    if not results:
        return _generic_fallback(coordinates, radius_miles, [], fitness_level)
    return results


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
     "description": "Forested trails leading to a drift-log beach on Puget Sound with tide pools.",
     "tags": ["beach", "forest", "family-friendly"]},
    {"name": "Point Defiance Park Trails", "lat": 47.3113, "lon": -122.5185,
     "type": "hiking", "difficulty": "easy", "miles": 5.0, "elev": 200,
     "description": "Old-growth forest with waterfront views, accessible family-friendly loops.",
     "tags": ["waterfront", "old-growth", "beach", "family-friendly"]},
    # ── Non-hiking: cycling ────────────────────────────────────────────────
    {"name": "Sammamish River Trail", "lat": 47.6800, "lon": -122.1200,
     "type": "cycling", "difficulty": "easy", "miles": 10.7, "elev": 70,
     "description": "Paved multi-use trail following the Sammamish River from Redmond to Bothell. Popular for families and fitness rides.",
     "tags": ["paved", "family-friendly", "riverside", "bike"]},
    {"name": "Burke-Gilman Trail (Redmond to Lake Forest Park)", "lat": 47.6712, "lon": -122.1061,
     "type": "cycling", "difficulty": "easy", "miles": 14.5, "elev": 100,
     "description": "Iconic Seattle-area paved trail connecting Redmond, Kenmore, and Lake Forest Park along the Sammamish River and Lake Washington.",
     "tags": ["paved", "lake-view", "bike", "multi-use"]},
    {"name": "Preston-Snoqualmie Trail", "lat": 47.5219, "lon": -121.9471,
     "type": "cycling", "difficulty": "moderate", "miles": 7.5, "elev": 600,
     "description": "Former railroad grade through second-growth forest from Preston to the Snoqualmie Valley. Gravel surface, gentle grade.",
     "tags": ["gravel", "forest", "bike", "rail-trail"]},
    {"name": "Coal Creek Trail", "lat": 47.5601, "lon": -122.1485,
     "type": "cycling", "difficulty": "easy", "miles": 4.0, "elev": 80,
     "description": "Paved connector trail through forested ravine between Bellevue and Factoria, good for a short leisure ride.",
     "tags": ["paved", "forest", "bike", "family-friendly"]},
    {"name": "Iron Horse State Park Trail (John Wayne Pioneer Trail)", "lat": 47.4063, "lon": -121.9835,
     "type": "cycling", "difficulty": "moderate", "miles": 25.0, "elev": 400,
     "description": "Former Milwaukee Road railroad grade, crushed gravel surface, following the Snoqualmie River past tunnels and trestles.",
     "tags": ["gravel", "rail-trail", "bike", "tunnel", "historic"]},
    # ── Non-hiking: kayaking / paddling ───────────────────────────────────
    {"name": "Lake Sammamish Kayak Launch (East Beach)", "lat": 47.5762, "lon": -122.0659,
     "type": "kayaking", "difficulty": "easy", "miles": 5.0, "elev": 0,
     "description": "Calm freshwater paddling on Lake Sammamish with mountain views. Rentals and launch access at the state park.",
     "tags": ["lake", "kayak", "paddle", "family-friendly"]},
    {"name": "Lake Union Kayak (Center for Wooden Boats)", "lat": 47.6260, "lon": -122.3374,
     "type": "kayaking", "difficulty": "easy", "miles": 4.0, "elev": 0,
     "description": "Paddling on Lake Union with views of Seattle skyline and houseboats. Rentals available at the Center for Wooden Boats.",
     "tags": ["lake", "kayak", "paddle", "urban", "views"]},
    {"name": "Snoqualmie River Paddle (Fall City)", "lat": 47.5728, "lon": -121.9129,
     "type": "kayaking", "difficulty": "moderate", "miles": 8.0, "elev": 0,
     "description": "Flatwater river paddle through farmland with views of the Cascade foothills. Class I-II riffles; appropriate for intermediate paddlers.",
     "tags": ["river", "kayak", "paddle", "scenic"]},
    # ── Non-hiking: beach / waterfront ────────────────────────────────────
    {"name": "Alki Beach Park", "lat": 47.5760, "lon": -122.4175,
     "type": "beach", "difficulty": "easy", "miles": 2.5, "elev": 0,
     "description": "Seattle's most popular urban beach with views of downtown, the Olympics, and ferry traffic. Walk, bike, or just relax.",
     "tags": ["beach", "waterfront", "family-friendly", "views", "accessible"]},
    {"name": "Saltwater State Park", "lat": 47.3640, "lon": -122.3169,
     "type": "beach", "difficulty": "easy", "miles": 2.0, "elev": 80,
     "description": "Quiet Puget Sound beach with a shallow cove for swimming, scuba diving, and beachcombing. Forested bluffs above.",
     "tags": ["beach", "diving", "picnic", "family-friendly"]},
    {"name": "Deception Pass State Park (Rosario Beach)", "lat": 48.4071, "lon": -122.6496,
     "type": "beach", "difficulty": "easy", "miles": 3.0, "elev": 100,
     "description": "Dramatic tidal shoreline with basalt formations, tide pools, and views of Deception Pass bridge. Short forest loop trail included.",
     "tags": ["beach", "tide-pools", "scenic", "family-friendly"]},
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
) -> tuple[list[ActivityResult], Literal["static_pnw", "static_template"]]:
    """Return curated PNW trails within radius, or generic template activities for non-PNW users.

    Returns (results, data_source) where data_source is 'static_pnw' or 'static_template'.
    Results preserve fitness-aware sort order: difficulty-match first, then haversine distance.
    """
    lat, lon = coordinates

    # Non-PNW users get generic templates (ISSUE-01)
    if not _is_in_pnw(lat, lon):
        results = _generic_fallback(coordinates, radius_miles, activity_types, fitness_level)
        if results:
            logger.info("Static fallback: non-PNW user (%g, %g) — returning %d template activities", lat, lon, len(results))
            return results, "static_template"
        return [], "static_template"

    # -- Update other static entries with descriptions too (sample for shorter ones) --
    # Note: Full descriptions are stored per-entry in _STATIC_PNW_TRAILS dict.

    type_lower = [t.lower() for t in activity_types]

    # Minimum difficulty tier for this fitness level
    min_diff = _FITNESS_MIN_DIFFICULTY.get(fitness_level.lower(), "easy")
    min_tier = _DIFFICULTY_ORDER.get(min_diff, 0)

    from nexus.tools.sanitize import sanitize_activity_name, sanitize_tool_text

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

        # ISSUE-16: sanitize name and description from static dataset
        safe_name = sanitize_activity_name(trail["name"])
        if safe_name is None:
            continue  # Drop activities with injected names entirely
        raw_desc = trail.get("description", "")
        safe_desc = sanitize_tool_text(raw_desc)

        results.append(ActivityResult(
            activity_id=f"static-{trail['name'].lower().replace(' ', '-')}",
            name=safe_name,
            location_coordinates=(trail["lat"], trail["lon"]),
            activity_type=trail["type"],
            difficulty=trail["difficulty"],
            elevation_gain_ft=trail["elev"],
            distance_miles=trail["miles"],
            description=safe_desc,
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

    return results[:20], "static_pnw"


class OverpassActivities:
    """
    Activity provider using Overpass API (OpenStreetMap).

    Falls back to a curated PNW static dataset when Overpass is unavailable
    or returns 0 named results.

    Args:
        cache: diskcache.Cache instance for result caching and circuit-breaker state.
               Pass None to disable caching (test context).
    """

    def __init__(self, cache: Cache | None = None) -> None:
        self._cache = cache

    async def search_activities(
        self,
        coordinates: Coordinates,
        radius_miles: float,
        activity_types: list[str],
        fitness_level: str = "intermediate",
    ) -> tuple[list[ActivityResult], Literal["live", "cached", "static_pnw", "static_template"]]:
        """Search for activities within radius_miles of coordinates.

        Returns (results, data_source) where data_source identifies the origin:
            'live'            — fresh Overpass API response
            'cached'          — stale-cache hit (Overpass was down)
            'static_pnw'      — curated PNW static dataset
            'static_template' — generic coordinate-offset template (non-PNW)
        """
        lat, lon = coordinates

        # ── Circuit-breaker: skip live fetch if cooldown is active ────────
        if self._cache is not None and self._cache.get(_OVERPASS_COOLDOWN_KEY):
            logger.info("Overpass circuit-breaker active — skipping live fetch, using static fallback")
            results, source = _static_fallback(coordinates, radius_miles, activity_types, fitness_level)
            return results, source

        # ── Build cache key ─────────────────────────────────────────
        type_key = ":".join(sorted(activity_types))
        cache_key = f"overpass:{lat:.2f},{lon:.2f}:{radius_miles}:{type_key}"

        # ── GracefulDegradation wrapper ────────────────────────────────
        from nexus.resilience import GracefulDegradation
        from nexus.state.confidence import DataConfidence

        static_results, static_source = _static_fallback(coordinates, radius_miles, activity_types, fitness_level)

        if self._cache is None:
            # Test context — no caching; run live fetch directly
            live = await self._live_fetch(coordinates, radius_miles, activity_types, fitness_level)
            if live:
                return live, "live"
            return static_results, static_source

        async def _fetcher() -> list[ActivityResult]:
            results = await self._live_fetch(coordinates, radius_miles, activity_types, fitness_level)
            if not results:
                raise RuntimeError("Overpass returned 0 named results")
            return results

        try:
            result, confidence = await GracefulDegradation.fetch_with_fallback(
                key=cache_key,
                fetcher=_fetcher,
                cache=self._cache,
                is_hard_constraint=False,
                default=static_results,
            )
        except Exception:
            return static_results, static_source

        # Map DataConfidence back to data_source literal
        if confidence == DataConfidence.VERIFIED:
            # Success — reset fail counter
            self._cache.delete(_OVERPASS_FAIL_COUNT_KEY)
            return result, "live"
        if confidence == DataConfidence.CACHED:
            return result, "cached"
        # ESTIMATED = default (static fallback)
        return static_results, static_source

    async def _live_fetch(
        self,
        coordinates: Coordinates,
        radius_miles: float,
        activity_types: list[str],
        fitness_level: str,
    ) -> list[ActivityResult]:
        """Attempt live Overpass fetch across mirrors. Updates circuit-breaker on failure."""
        lat, lon = coordinates
        radius_meters = int(radius_miles * 1609)
        is_hiking = any("hik" in t.lower() or "trail" in t.lower() or "outdoor" in t.lower()
                        for t in activity_types)

        tags = _activity_types_to_tags(activity_types)
        query_parts: list[str] = []

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

        if not is_hiking:
            query_parts.append(
                f'  way["leisure"~"park|nature_reserve"]["name"](around:{radius_meters},{lat},{lon});'
            )
        else:
            query_parts.append(
                f'  way["leisure"="nature_reserve"]["name"](around:{radius_meters},{lat},{lon});'
            )

        overpass_query = (
            "[out:json][timeout:25];\n(\n"
            + "\n".join(query_parts)
            + "\n);\nout center 30;"
        )

        _HEADERS = {"User-Agent": "nexus-planner/1.0 (weekend-activity-planner)"}
        from nexus.resilience import GracefulDegradation

        for endpoint in OVERPASS_ENDPOINTS:
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT, headers=_HEADERS) as client:
                    resp = await client.post(endpoint, data={"data": overpass_query})
                    if resp.status_code == 429:
                        # Rate-limited — terminal; break immediately (ISSUE-03)
                        logger.info("Overpass %s → rate limited (429); skipping remaining mirrors", endpoint)
                        self._increment_fail_counter()
                        break
                    if resp.status_code == 200:
                        data = resp.json()
                        results = _parse_overpass_results(data, activity_types, fitness_level)
                        if results:
                            logger.debug("Overpass: %d results from %s", len(results), endpoint)
                            return results
                        logger.debug("Overpass: 0 named results from %s", endpoint)
                    else:
                        logger.warning("Overpass %s -> HTTP %d", endpoint, resp.status_code)
                        self._increment_fail_counter()
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning("Overpass %s failed: %s", endpoint, e)
                self._increment_fail_counter()
            except httpx.HTTPError as e:
                logger.warning("Overpass %s failed: %s", endpoint, e)
                self._increment_fail_counter()

        return []

    def _increment_fail_counter(self) -> None:
        """Increment the circuit-breaker failure counter; activate cooldown at threshold."""
        if self._cache is None:
            return
        count = self._cache.get(_OVERPASS_FAIL_COUNT_KEY, 0) + 1
        self._cache.set(_OVERPASS_FAIL_COUNT_KEY, count, expire=_CIRCUIT_BREAKER_WINDOW_S)
        if count >= _CIRCUIT_BREAKER_THRESHOLD:
            self._cache.set(_OVERPASS_COOLDOWN_KEY, True, expire=_CIRCUIT_BREAKER_COOLDOWN_S)
            logger.warning(
                "Overpass circuit-breaker activated after %d failures — "
                "live fetch paused for %d seconds",
                count, _CIRCUIT_BREAKER_COOLDOWN_S,
            )


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

        # ISSUE-16: sanitize name; drop elements with injected names
        from nexus.tools.sanitize import sanitize_activity_name, sanitize_tool_text
        safe_name = sanitize_activity_name(name)
        if safe_name is None:
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

        # ISSUE-16: sanitize description from OSM tags
        raw_desc = tags.get("description", "")
        safe_desc = sanitize_tool_text(raw_desc)

        results.append(ActivityResult(
            activity_id=f"osm-{element.get('id', name)}",
            name=safe_name,
            location_coordinates=(lat, lon),
            activity_type=detected_type,
            difficulty=difficulty,
            elevation_gain_ft=elev_gain,
            distance_miles=raw_dist_miles,
            description=safe_desc,
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
