"""
Shared pytest fixtures for all test phases.

Lazy import rule: ALL imports inside fixture function bodies (never at module top-level).
This prevents collection-time ImportError when later phases are not yet implemented.
Phase 1 tests never call Phase 3+ fixtures, so deferred imports are safe.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Config fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_config():
    """Load NexusConfig from the shared test fixture YAML."""
    from nexus.config import NexusConfig  # lazy import

    return NexusConfig.load(profile_path=FIXTURES_DIR / "sample_profile.yaml")


@pytest.fixture
def minimal_config(tmp_path):
    """Minimal NexusConfig with tmp_path as base_dir for isolation."""
    from nexus.config import NexusConfig, PathsConfig  # lazy import

    config = NexusConfig()
    config.paths = PathsConfig(base_dir=tmp_path / ".nexus")
    return config


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: State fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def initial_state(sample_config):
    """A valid initial WeekendPlanState for graph tests."""
    from nexus.state.helpers import build_initial_state  # lazy import

    return build_initial_state(
        user_intent="hike with the family on Sunday",
        config=sample_config,
        request_id="test-request-001",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Weather fixtures (used by Phase 5 meteorology tests)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def weather_clear():
    """Clear weather — meteorology agent should APPROVE."""
    from datetime import datetime, timezone  # lazy import

    from nexus.tools.models import AirQuality, DaylightWindow, WeatherForecast  # lazy import

    now = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
    return WeatherForecast(
        precipitation_probability=5.0,
        lightning_risk=False,
        conditions_text="Sunny with light clouds",
        temperature_high_f=72.0,
        data_age_minutes=0,
        confidence="verified",
        aqi=AirQuality(aqi=42, data_age_minutes=0, confidence="verified"),
        daylight=DaylightWindow(
            sunrise=now.replace(hour=6, minute=30),
            sunset=now.replace(hour=19, minute=45),
            data_age_minutes=0,
            confidence="verified",
        ),
    )


@pytest.fixture
def weather_rainy():
    """Rainy weather (65% precip) — meteorology agent should REJECT."""
    from datetime import datetime, timezone  # lazy import

    from nexus.tools.models import AirQuality, DaylightWindow, WeatherForecast  # lazy import

    now = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
    return WeatherForecast(
        precipitation_probability=65.0,
        lightning_risk=False,
        conditions_text="Heavy rain expected",
        temperature_high_f=58.0,
        data_age_minutes=0,
        confidence="verified",
        aqi=AirQuality(aqi=35, data_age_minutes=0, confidence="verified"),
        daylight=DaylightWindow(
            sunrise=now.replace(hour=6, minute=45),
            sunset=now.replace(hour=19, minute=30),
            data_age_minutes=0,
            confidence="verified",
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3+: Mock fixtures (lazy imports prevent Phase 1 import failures)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_tool_registry():
    """
    Duck-typed mock satisfying ToolRegistry.get() interface.
    Does NOT instantiate real ToolRegistry (Phase 3 providers don't exist yet).
    """
    registry = MagicMock()
    registry.get.return_value = MagicMock()
    return registry


@pytest.fixture
def mock_llm():
    """
    Mock ChatOllama that returns predictable structured output without Ollama running.
    Returned value is an AsyncMock that can be used as ainvoke() target.
    """
    from nexus.state.schemas import AgentVerdict  # lazy import

    mock = AsyncMock()
    # Default structured output — tests override per-fixture
    mock.ainvoke.return_value = AgentVerdict(
        agent_name="mock",
        verdict="APPROVED",
        is_hard_constraint=False,
        confidence=0.9,
    )
    mock.with_structured_output.return_value = mock
    return mock


@pytest.fixture
def mock_model_router(mock_llm):
    """Mock ModelRouter that returns mock_llm for any agent."""
    router = MagicMock()
    router.get_model.return_value = mock_llm
    return router
