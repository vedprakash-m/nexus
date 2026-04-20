"""
Resilience primitives: failure classification, error types, graceful degradation.

This module is imported by both the tool layer (Phase 3) and agent layer (Phase 5).
It must NOT import from nexus.state or nexus.agents to avoid circular imports.
"""

from __future__ import annotations

import asyncio
import logging
import random
from enum import Enum
from typing import Awaitable, Callable, TypeVar

from diskcache import Cache

from nexus.state.confidence import DataConfidence

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AgentFailureType(str, Enum):
    """Classifies why an agent produced a non-APPROVED verdict."""

    DATA_UNAVAILABLE = "data_unavailable"  # Required data couldn't be fetched
    HARD_CONSTRAINT_BLOCK = "hard_constraint_block"  # Rule-based block
    TIMEOUT = "timeout"  # asyncio.TimeoutError
    INTERNAL_ERROR = "internal_error"  # Unexpected exception


class HardConstraintDataUnavailable(Exception):
    """
    Raised by fetch_with_fallback() when a hard-constraint agent needs data
    that is unavailable live AND has no stale cache entry.

    Caught by agent_error_boundary to produce a REJECTED verdict with
    failure_type=DATA_UNAVAILABLE and halt the planning loop.
    """

    def __init__(self, constraint_name: str, detail: str = "") -> None:
        self.constraint_name = constraint_name
        self.detail = detail  # user-facing message, free of internal names
        super().__init__(
            f"Hard constraint data unavailable: {constraint_name}"
            + (f" — {detail}" if detail else "")
        )


class GracefulDegradation:
    """
    Implements the PRD graceful degradation contract for all external data fetches.

    Waterfall:
        1. Live fetch with 3 retries + exponential backoff
        2. Stale cache (stale:{key} prefix, expire=None)
        3a. Hard constraint → raise HardConstraintDataUnavailable
        3b. Soft constraint → return (default, DataConfidence.ESTIMATED)
    """

    @staticmethod
    async def fetch_with_fallback(
        key: str,
        fetcher: Callable[[], Awaitable[T]],
        cache: Cache,
        is_hard_constraint: bool,
        default: T | None = None,
    ) -> tuple[T, DataConfidence]:
        """
        Fetch data with live-first, stale-cache fallback, degraded-default last resort.

        Args:
            key: Cache lookup string, e.g. "weather:37.7,-122.4:2026-04-19"
            fetcher: Zero-arg async callable that performs the live API fetch.
            cache: diskcache.Cache instance for read/write.
            is_hard_constraint: If True and all fallbacks fail, raises
                HardConstraintDataUnavailable instead of returning a default.
            default: Value to return when soft-constraint data is unavailable.

        Returns:
            (result, DataConfidence) tuple.
        """
        stale_key = f"stale:{key}"

        # --- 1. Live fetch with exponential backoff ---
        delays = [0.5, 1.0, 2.0]
        last_error: Exception | None = None

        for attempt, delay in enumerate(delays):
            try:
                result = await fetcher()
                # Write fresh data to both the TTL key and the permanent stale key
                cache[key] = result  # TTL set by caller via cache.set() or tag
                cache.set(stale_key, result, expire=None)  # never expires
                return (result, DataConfidence.VERIFIED)
            except Exception as exc:
                last_error = exc
                # Only retry on transient errors
                if GracefulDegradation._is_terminal_error(exc):
                    logger.warning("Terminal error fetching %s: %s", key, exc)
                    break
                if attempt < len(delays) - 1:
                    jitter = random.uniform(-0.1, 0.1)  # noqa: S311
                    await asyncio.sleep(delay + jitter)
                    logger.debug("Retry %d/%d for %s", attempt + 1, len(delays), key)

        logger.warning("Live fetch failed for %s: %s", key, last_error)

        # --- 2. Stale cache fallback ---
        stale = cache.get(stale_key)
        if stale is not None:
            logger.info("Using stale cache for %s", key)
            return (stale, DataConfidence.CACHED)

        # --- 3. No data at all ---
        if is_hard_constraint:
            raise HardConstraintDataUnavailable(
                constraint_name=key,
                detail=f"Live fetch failed: {last_error}; no stale cache available",
            )

        if default is not None:
            logger.warning("No data for soft constraint %s — using default", key)
            return (default, DataConfidence.ESTIMATED)

        raise HardConstraintDataUnavailable(
            constraint_name=key,
            detail="No default value provided for soft constraint with no data",
        )

    @staticmethod
    def _is_terminal_error(exc: Exception) -> bool:
        """Return True for errors that should NOT be retried."""
        import httpx  # local import to avoid circular

        if isinstance(exc, httpx.HTTPStatusError):
            # 401/403 = auth/config error, not transient
            return exc.response.status_code in (401, 403)
        return False
