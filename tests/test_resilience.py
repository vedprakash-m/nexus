"""
Unit tests for GracefulDegradation._is_terminal_error() — ISSUE-05/ISSUE-10.

Verifies which exception types cause immediate abandonment (terminal) versus
triggering the exponential-backoff retry loop (transient).
"""

from __future__ import annotations

import httpx

from nexus.resilience import GracefulDegradation


class TestIsTerminalError:
    # ── Terminal: should NOT be retried ──────────────────────────────────────

    def test_401_is_terminal(self):
        resp = httpx.Response(401)
        exc = httpx.HTTPStatusError(
            "unauthorized", request=httpx.Request("GET", "http://x"), response=resp
        )
        assert GracefulDegradation._is_terminal_error(exc) is True

    def test_403_is_terminal(self):
        resp = httpx.Response(403)
        exc = httpx.HTTPStatusError(
            "forbidden", request=httpx.Request("GET", "http://x"), response=resp
        )
        assert GracefulDegradation._is_terminal_error(exc) is True

    def test_429_is_terminal(self):
        """Rate-limited: retrying worsens the rate-limit window (ISSUE-03)."""
        resp = httpx.Response(429)
        exc = httpx.HTTPStatusError(
            "rate limited", request=httpx.Request("GET", "http://x"), response=resp
        )
        assert GracefulDegradation._is_terminal_error(exc) is True

    def test_connect_error_is_terminal(self):
        """ConnectError = server definitively unreachable; immediate retry is futile (ISSUE-10)."""
        exc = httpx.ConnectError("connection refused")
        assert GracefulDegradation._is_terminal_error(exc) is True

    # ── Transient: should be retried ─────────────────────────────────────────

    def test_500_is_transient(self):
        resp = httpx.Response(500)
        exc = httpx.HTTPStatusError(
            "server error", request=httpx.Request("GET", "http://x"), response=resp
        )
        assert GracefulDegradation._is_terminal_error(exc) is False

    def test_503_is_transient(self):
        resp = httpx.Response(503)
        exc = httpx.HTTPStatusError(
            "unavailable", request=httpx.Request("GET", "http://x"), response=resp
        )
        assert GracefulDegradation._is_terminal_error(exc) is False

    def test_timeout_is_transient(self):
        exc = httpx.TimeoutException("timed out")
        assert GracefulDegradation._is_terminal_error(exc) is False

    def test_remote_protocol_error_is_transient(self):
        exc = httpx.RemoteProtocolError("peer closed connection")
        assert GracefulDegradation._is_terminal_error(exc) is False

    def test_generic_exception_is_transient(self):
        assert GracefulDegradation._is_terminal_error(RuntimeError("boom")) is False


class TestFetchWithFallbackTerminalBehavior:
    """Verify that terminal errors skip retries and proceed to cache/default."""

    async def test_connect_error_skips_retries(self, tmp_path):
        """ConnectError should cause fetch_with_fallback to skip retries immediately."""
        from diskcache import Cache
        from nexus.state.confidence import DataConfidence

        call_count = 0

        async def _fetcher():
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("connection refused")

        with Cache(str(tmp_path / "cache")) as cache:
            value, confidence = await GracefulDegradation.fetch_with_fallback(
                key="test:connect_error",
                fetcher=_fetcher,
                cache=cache,
                is_hard_constraint=False,
                default="fallback",
            )

        assert call_count == 1, f"ConnectError must not be retried; got {call_count} calls"
        assert value == "fallback"
        assert confidence == DataConfidence.ESTIMATED

    async def test_timeout_triggers_retries(self, tmp_path):
        """TimeoutException is transient — should trigger up to 3 attempts."""
        from diskcache import Cache

        call_count = 0

        async def _fetcher():
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("timed out")

        with Cache(str(tmp_path / "cache")) as cache:
            await GracefulDegradation.fetch_with_fallback(
                key="test:timeout",
                fetcher=_fetcher,
                cache=cache,
                is_hard_constraint=False,
                default="fallback",
            )

        assert call_count == 3, f"TimeoutException should retry 3 times; got {call_count}"
