"""
Preflight-check tests — task 8.4.

All external side-effects (socket, shutil.which, subprocess, psutil, os.statvfs)
are patched so the test suite works without Ollama or extra disk space.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


# ── helpers ──────────────────────────────────────────────────────────────────


def _statvfs(free_gb: float) -> MagicMock:
    """Build a fake os.statvfs_result with the given free gigabytes."""
    blk = 4096
    free_blocks = int(free_gb * (1024**3) / blk)
    stat = MagicMock()
    stat.f_bavail = free_blocks
    stat.f_frsize = blk
    return stat


def _psutil_mem(available_gb: float) -> MagicMock:
    mem = MagicMock()
    mem.available = int(available_gb * 1024**3)
    return mem


# ── happy-path: all checks pass ──────────────────────────────────────────────


class TestPreflightAllPass:
    def test_can_start_and_all_ok(self, tmp_path: Path) -> None:
        """When every dependency is healthy, can_start and all_ok are both True."""
        from nexus.cli.preflight import run_preflight

        with (
            patch("socket.socket") as mock_sock_cls,
            patch("shutil.which", return_value="/usr/local/bin/ollama"),
            patch("socket.create_connection"),  # Ollama TCP check passes
            patch(
                "subprocess.run",
                return_value=MagicMock(stdout="qwen3:8b latest …", returncode=0),
            ),
            patch("os.statvfs", return_value=_statvfs(40.0)),
            patch("psutil.virtual_memory", return_value=_psutil_mem(16.0)),
        ):
            # Port check: bind succeeds
            ctx = MagicMock()
            mock_sock_cls.return_value.__enter__ = lambda *_: ctx
            mock_sock_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = run_preflight(port=9999, nexus_dir=tmp_path)

        assert result.can_start, f"Expected can_start=True; issues: {result.issues}"
        assert result.all_ok, f"Expected all_ok=True; issues: {result.issues}"
        assert result.issues == []


# ── Ollama not installed ──────────────────────────────────────────────────────


class TestPreflightOllamaMissing:
    def test_ollama_missing_is_critical_failure(self, tmp_path: Path) -> None:
        from nexus.cli.preflight import run_preflight

        with (
            patch("socket.socket"),
            patch("shutil.which", return_value=None),  # ollama not on PATH
            patch("socket.create_connection", side_effect=OSError("refused")),
            patch("os.statvfs", return_value=_statvfs(40.0)),
            patch("psutil.virtual_memory", return_value=_psutil_mem(16.0)),
        ):
            result = run_preflight(port=9999, nexus_dir=tmp_path)

        ollama_check = next((c for c in result.checks if c.name == "Ollama installed"), None)
        assert ollama_check is not None
        assert ollama_check.status is False
        assert ollama_check.is_critical is True
        assert result.can_start is False

    def test_ollama_missing_includes_fix_action(self, tmp_path: Path) -> None:
        from nexus.cli.preflight import run_preflight

        with (
            patch("socket.socket"),
            patch("shutil.which", return_value=None),
            patch("socket.create_connection", side_effect=OSError("refused")),
            patch("os.statvfs", return_value=_statvfs(40.0)),
            patch("psutil.virtual_memory", return_value=_psutil_mem(16.0)),
        ):
            result = run_preflight(port=9999, nexus_dir=tmp_path)

        ollama_check = next(c for c in result.checks if c.name == "Ollama installed")
        assert "ollama.ai" in ollama_check.fix_action.lower()


# ── Port busy ────────────────────────────────────────────────────────────────


class TestPreflightPortBusy:
    def test_busy_port_is_non_critical_warning(self, tmp_path: Path) -> None:
        """Port conflict is a warning (can_start=True) but appears in issues."""
        from nexus.cli.preflight import run_preflight

        def _busy_bind(*_args, **_kwargs):
            raise OSError(98, "Address already in use")

        with (
            patch("socket.socket") as mock_sock_cls,
            patch("shutil.which", return_value="/usr/local/bin/ollama"),
            patch("socket.create_connection"),
            patch(
                "subprocess.run",
                return_value=MagicMock(stdout="qwen3:8b latest …", returncode=0),
            ),
            patch("os.statvfs", return_value=_statvfs(40.0)),
            patch("psutil.virtual_memory", return_value=_psutil_mem(16.0)),
        ):
            ctx = MagicMock()
            ctx.bind = _busy_bind
            mock_sock_cls.return_value.__enter__ = lambda *_: ctx
            mock_sock_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = run_preflight(port=9999, nexus_dir=tmp_path)

        port_check = next((c for c in result.checks if "Port" in c.name), None)
        assert port_check is not None
        assert port_check.status is False
        assert port_check.is_critical is False
        # can_start ignores non-critical failures
        assert result.can_start is True
        assert any("port" in issue.lower() for issue in result.issues)


# ── Low disk space ────────────────────────────────────────────────────────────


class TestPreflightDiskSpace:
    def test_low_disk_is_non_critical_warning(self, tmp_path: Path) -> None:
        """< 15 GB free is a warning, not a hard block."""
        from nexus.cli.preflight import run_preflight

        with (
            patch("socket.socket"),
            patch("shutil.which", return_value="/usr/local/bin/ollama"),
            patch("socket.create_connection"),
            patch(
                "subprocess.run",
                return_value=MagicMock(stdout="qwen3:8b latest …", returncode=0),
            ),
            patch("os.statvfs", return_value=_statvfs(5.0)),  # 5 GB — under 15 GB threshold
            patch("psutil.virtual_memory", return_value=_psutil_mem(16.0)),
        ):
            result = run_preflight(port=9999, nexus_dir=tmp_path)

        disk_check = next((c for c in result.checks if c.name == "Disk space"), None)
        assert disk_check is not None
        assert disk_check.status is False
        assert disk_check.is_critical is False
        assert result.can_start is True  # Non-critical — server can still start

    def test_ample_disk_passes(self, tmp_path: Path) -> None:
        from nexus.cli.preflight import run_preflight

        with (
            patch("socket.socket"),
            patch("shutil.which", return_value="/usr/local/bin/ollama"),
            patch("socket.create_connection"),
            patch(
                "subprocess.run",
                return_value=MagicMock(stdout="qwen3:8b latest …", returncode=0),
            ),
            patch("os.statvfs", return_value=_statvfs(100.0)),
            patch("psutil.virtual_memory", return_value=_psutil_mem(16.0)),
        ):
            result = run_preflight(port=9999, nexus_dir=tmp_path)

        disk_check = next(c for c in result.checks if c.name == "Disk space")
        assert disk_check.status is True


# ── PreflightResult helpers ───────────────────────────────────────────────────


class TestPreflightResult:
    def test_issues_lists_failed_fix_actions(self) -> None:
        from nexus.cli.preflight import CheckResult, PreflightResult

        result = PreflightResult(
            checks=[
                CheckResult("A", status=True, message="ok"),
                CheckResult("B", status=False, message="bad", fix_action="Do X", is_critical=True),
                CheckResult("C", status=False, message="low", fix_action="Do Y", is_critical=False),
            ]
        )
        assert "Do X" in result.issues
        assert "Do Y" in result.issues
        assert len(result.issues) == 2

    def test_can_start_requires_all_critical_pass(self) -> None:
        from nexus.cli.preflight import CheckResult, PreflightResult

        ok = CheckResult("Port", status=True, message="free", is_critical=True)
        critical_fail = CheckResult("Ollama", status=False, message="missing", is_critical=True)
        non_critical_fail = CheckResult("Disk", status=False, message="low", is_critical=False)

        assert PreflightResult(checks=[ok, non_critical_fail]).can_start is True
        assert PreflightResult(checks=[ok, critical_fail]).can_start is False
