"""Tests for NexusConfig loading, defaults, and .env parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_load_sample_config(sample_config):
    """Config loads from sample_profile.yaml correctly."""
    assert sample_config.user.name == "Alex"
    assert sample_config.user.fitness_level == "advanced"
    assert "vegetarian" in sample_config.user.dietary_restrictions
    assert sample_config.family.max_total_driving_minutes == 180
    assert len(sample_config.family.members) == 3


def test_family_members(sample_config):
    """Family member data parsed correctly."""
    members_by_name = {m.name: m for m in sample_config.family.members}
    assert "Sarah" in members_by_name
    assert "Emma" in members_by_name
    assert members_by_name["Emma"].requires_cell_service is True
    assert members_by_name["Jake"].age == 12


def test_default_values(minimal_config):
    """Default NexusConfig values are sane."""
    assert minimal_config.models.local_model == "qwen3.5:9b"
    assert minimal_config.planning.max_iterations == 3
    assert minimal_config.planning.precipitation_threshold_pct == 40
    assert minimal_config.ollama.base_url == "http://localhost:11434"
    assert minimal_config.models.cloud_agents.enabled is False


def test_paths_derived_from_base_dir(minimal_config, tmp_path):
    """PathsConfig derives subdirectories from base_dir."""
    base = tmp_path / ".nexus"
    from nexus.config import PathsConfig

    paths = PathsConfig(base_dir=base)
    assert paths.plans_dir == base / "plans"
    assert paths.cache_dir == base / "cache"
    assert paths.checkpoint_db == base / "checkpoints" / "nexus.db"
    assert paths.logs_dir == base / "logs"


def test_missing_file_raises_clear_error(tmp_path):
    """Loading from nonexistent path raises FileNotFoundError with message."""
    from nexus.config import NexusConfig

    with pytest.raises(FileNotFoundError, match="Profile not found"):
        NexusConfig.load(profile_path=tmp_path / "nonexistent.yaml")


def test_env_parsing(tmp_path):
    """_parse_env handles comments, quoted values, blank lines."""
    from nexus.config import _parse_env

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Google Places API key\n"
        "GOOGLE_PLACES_API_KEY=abc123\n"
        "HIKING_PROJECT_KEY='quoted_value'\n"
        "\n"
        "EMPTY_KEY=\n"
        "# Another comment\n"
        "DOUBLE_QUOTED=\"double_quoted\"\n"
    )
    result = _parse_env(env_file)
    assert result["GOOGLE_PLACES_API_KEY"] == "abc123"
    assert result["HIKING_PROJECT_KEY"] == "quoted_value"
    assert result["DOUBLE_QUOTED"] == "double_quoted"
    assert "EMPTY_KEY" not in result  # empty values excluded


def test_env_loaded_alongside_profile(tmp_path):
    """API keys from .env are merged into config.tools.api_keys."""
    import shutil

    from nexus.config import NexusConfig

    # Copy fixture profile to tmp dir
    fixture = FIXTURES_DIR / "sample_profile.yaml"
    profile = tmp_path / "profile.yaml"
    shutil.copy(fixture, profile)

    # Create .env
    (tmp_path / ".env").write_text("GOOGLE_PLACES_API_KEY=test_key_123\n")

    config = NexusConfig.load(profile_path=profile)
    assert config.tools.api_keys.get("GOOGLE_PLACES_API_KEY") == "test_key_123"


def test_config_roundtrip(tmp_path, sample_config):
    """Config can be saved and reloaded without data loss."""
    out = tmp_path / "profile.yaml"
    sample_config.save(profile_path=out)
    assert out.exists()

    from nexus.config import NexusConfig

    reloaded = NexusConfig.load(profile_path=out)
    assert reloaded.user.name == sample_config.user.name
    assert reloaded.planning.max_iterations == sample_config.planning.max_iterations
