"""
Cache factory using diskcache.

diskcache uses SQLite internally — zero-infrastructure caching
that survives process restarts and supports per-entry TTL expiry.
"""

from __future__ import annotations

from pathlib import Path

from diskcache import Cache


def create_cache(cache_dir: Path) -> Cache:
    """
    Create a diskcache instance at the given directory.

    Size limit: 500MB per Tech §11.1.
    The diskcache directory is created if it doesn't exist.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    return Cache(str(cache_dir), size_limit=500 * 1024 * 1024)  # 500MB
