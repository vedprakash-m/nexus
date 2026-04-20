"""Data confidence enum — indicates how fresh/reliable a data point is."""

from enum import Enum


class DataConfidence(str, Enum):
    """
    Tracks the source reliability of any external data used in planning.

    Used by the tool layer and surfaced as confidence labels in the plan output.
    Template renders: VERIFIED="", CACHED="(Xhr cache)", ESTIMATED="(est.)"
    """

    VERIFIED = "verified"  # Fresh live data, fetched successfully this run
    CACHED = "cached"  # Read from stale diskcache fallback (expired TTL)
    ESTIMATED = "estimated"  # No live or cached data — heuristic/default used
