"""
Cell coverage heuristic estimator.

Uses road proximity (via OSRM) as a proxy for cell coverage.
OSM has no signal data — this is a best-effort heuristic only.

Rule of thumb: within 0.5 miles of a major road → likely coverage.

Tech spec §4.5: estimate_cell_coverage() returns a CoverageEstimate
with has_likely_service=True/False and road_proximity_miles.
"""

from __future__ import annotations

from nexus.tools.models import Coordinates, CoverageEstimate

# Default distance threshold: roads within this → likely has service.
# Overridden at call-site by config.planning.cell_coverage_road_proximity_miles.
ROAD_PROXIMITY_THRESHOLD_MILES = 1.0


async def estimate_cell_coverage(
    coordinates: Coordinates,
    routing_tool: object,
    road_proximity_threshold_miles: float = ROAD_PROXIMITY_THRESHOLD_MILES,
) -> CoverageEstimate:
    """
    Estimate cell coverage at a location using road proximity heuristic.

    Args:
        coordinates: (lat, lon) of the location to check.
        routing_tool: a RoutingTool implementation with nearest_road_distance().
        road_proximity_threshold_miles: roads closer than this are treated as
            "has coverage". Configurable via planning.cell_coverage_road_proximity_miles.

    Returns:
        CoverageEstimate with has_likely_service and road_proximity_miles.
    """
    try:
        distance_miles: float = await routing_tool.nearest_road_distance(coordinates)  # type: ignore[attr-defined]
    except Exception:
        # If routing fails, assume poor coverage for safety
        return CoverageEstimate(
            has_likely_service=False,
            road_proximity_miles=999.0,
            poor_coverage_percentage=100.0,
            data_age_minutes=0,
            confidence="estimated",
        )

    has_service = distance_miles <= road_proximity_threshold_miles

    return CoverageEstimate(
        has_likely_service=has_service,
        road_proximity_miles=distance_miles,
        poor_coverage_percentage=0.0 if has_service else 100.0,
        data_age_minutes=0,
        confidence="estimated",  # Always estimated — no real signal data
    )
