"""
Preflight checks before server launch — Tech §9.1.1.

Checks (fast→slow):
1. Port availability
2. Ollama installed
3. Ollama running (HTTP)
4. Model available
5. Disk space
6. RAM availability
"""

from __future__ import annotations

import shutil
import socket
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckResult:
    name: str
    status: bool
    message: str
    fix_action: str = ""
    is_critical: bool = True


@dataclass
class PreflightResult:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def can_start(self) -> bool:
        """True if all critical checks pass."""
        return all(c.status or not c.is_critical for c in self.checks)

    @property
    def all_ok(self) -> bool:
        return all(c.status for c in self.checks)

    @property
    def issues(self) -> list[str]:
        return [c.fix_action or c.message for c in self.checks if not c.status]


def run_preflight(port: int = 7820, nexus_dir: Path | None = None) -> PreflightResult:
    """Run all preflight checks and return a PreflightResult."""
    result = PreflightResult()
    base_dir = nexus_dir or (Path.home() / ".nexus")

    # 1. Port availability
    result.checks.append(_check_port(port))

    # 2. Ollama installed
    ollama_installed = shutil.which("ollama") is not None
    result.checks.append(
        CheckResult(
            name="Ollama installed",
            status=ollama_installed,
            message="Ollama found" if ollama_installed else "Ollama not installed",
            fix_action="Install Ollama from https://ollama.ai",
            is_critical=True,
        )
    )

    # 3. Ollama running
    ollama_running = _check_ollama_running()
    result.checks.append(
        CheckResult(
            name="Ollama running",
            status=ollama_running,
            message="Ollama is running" if ollama_running else "Ollama is not running",
            fix_action="Run: ollama serve",
            is_critical=True,
        )
    )

    # 4. Model available (only check if Ollama is running)
    if ollama_running:
        model_ok, model_msg = _check_model("qwen3:8b")
        result.checks.append(
            CheckResult(
                name="Model available",
                status=model_ok,
                message=model_msg,
                fix_action="Run: ollama pull qwen3:8b",
                is_critical=True,
            )
        )
    else:
        result.checks.append(
            CheckResult(
                name="Model available",
                status=False,
                message="Cannot check — Ollama not running",
                fix_action="Start Ollama first (ollama serve)",
                is_critical=True,
            )
        )

    # 5. Disk space (warn if < 15GB free)
    result.checks.append(_check_disk_space(base_dir))

    # 6. RAM availability (warn if < 10GB available)
    result.checks.append(_check_ram())

    return result


def _check_port(port: int) -> CheckResult:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
        return CheckResult(
            name=f"Port {port} available",
            status=True,
            message=f"Port {port} is free",
            is_critical=True,
        )
    except OSError:
        return CheckResult(
            name=f"Port {port} available",
            status=False,
            message=f"Port {port} is already in use",
            fix_action=f"Stop the process using port {port}, or use --port to pick another",
            is_critical=False,  # Server can try a different port
        )


def _check_ollama_running() -> bool:
    """Quick TCP check on Ollama's default port."""
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=2):
            return True
    except OSError:
        return False


def _check_model(model_name: str) -> tuple[bool, str]:
    try:
        import subprocess
        output = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10
        )
        if model_name in output.stdout:
            return True, f"Model '{model_name}' is available"
        return False, f"Model '{model_name}' not found"
    except Exception:
        return False, "Could not check model list"


def _check_disk_space(base_dir: Path) -> CheckResult:
    import os
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        stat = os.statvfs(str(base_dir))
        free_gb = stat.f_bavail * stat.f_frsize / (1024 ** 3)
        ok = free_gb >= 15.0
        return CheckResult(
            name="Disk space",
            status=ok,
            message=f"{free_gb:.1f} GB free",
            fix_action="Free space on the drive containing ~/.nexus",
            is_critical=False,  # Low disk is a warning, not a hard blocker
        )
    except Exception:
        return CheckResult(
            name="Disk space",
            status=True,
            message="Could not check disk space",
            is_critical=False,
        )


def _check_ram() -> CheckResult:
    try:
        import psutil  # type: ignore[import-untyped]
        available_gb = psutil.virtual_memory().available / (1024 ** 3)
        if available_gb < 4.0:
            return CheckResult(
                name="RAM",
                status=False,
                message=f"Only {available_gb:.1f} GB available — need ≥4 GB",
                fix_action="Close other applications to free RAM",
                is_critical=True,
            )
        if available_gb < 10.0:
            return CheckResult(
                name="RAM",
                status=False,
                message=f"{available_gb:.1f} GB available — 9B model needs ≥10 GB",
                fix_action="Close other applications or use a smaller model",
                is_critical=False,  # Warning only
            )
        return CheckResult(
            name="RAM",
            status=True,
            message=f"{available_gb:.1f} GB available",
            is_critical=False,
        )
    except ImportError:
        return CheckResult(
            name="RAM",
            status=True,
            message="psutil not installed — RAM check skipped",
            is_critical=False,
        )
    except Exception:
        return CheckResult(
            name="RAM",
            status=True,
            message="Could not check RAM",
            is_critical=False,
        )
