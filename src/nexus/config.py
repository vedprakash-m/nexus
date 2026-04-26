"""
NexusConfig — loads user profile from ~/.nexus/profile.yaml + .env.

Import rules: this module MUST NOT import from nexus.state or nexus.agents.
State schemas (nexus.state.schemas) import from nexus.config — one-way dependency.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Config sub-models (no nexus imports)
# ─────────────────────────────────────────────────────────────────────────────


class ModelCloudConfig(BaseModel):
    enabled: bool = False
    model: str = "qwen3.5:cloud"
    agents: list[str] = Field(default_factory=list)


class ModelsConfig(BaseModel):
    local_model: str = "qwen3.5:9b"
    cloud_agents: ModelCloudConfig = Field(default_factory=ModelCloudConfig)


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"


class ToolProvidersConfig(BaseModel):
    weather: str = "open_meteo"
    activity: str = "overpass"
    places: str = "google"
    routing: str = "osrm"


class ToolsConfig(BaseModel):
    providers: ToolProvidersConfig = Field(default_factory=ToolProvidersConfig)
    api_keys: dict[str, str] = Field(default_factory=dict)  # loaded from .env


class PlanningConfig(BaseModel):
    max_iterations: int = 3
    default_search_radius_miles: float = 50.0
    precipitation_threshold_pct: int = 40
    aqi_threshold: int = 100
    min_sunset_buffer_minutes: int = 30
    # Cell coverage heuristic: road distance (miles) below which coverage is assumed.
    # Increase to pass more remote trailheads; set to 0.0 to disable the check entirely.
    cell_coverage_road_proximity_miles: float = 1.0
    # Whether a teen family member alone triggers the cell-coverage hard reject.
    # False (default) means only members with requires_cell_service=true are enforced.
    require_teen_cell_service: bool = False
    # Logistics constraints — set to 0 / large values to relax.
    earliest_departure_hour: int = 6
    max_day_hours: float = 12.0
    # Restaurant search radius from the activity endpoint. Raise for remote trailheads
    # (e.g. 30.0 to find a town on the drive home).
    restaurant_search_radius_miles: float = 10.0
    # Safety: precip % at or above which hospital proximity is also checked (family plans).
    # Lower = stricter; raise or set to 100 to skip the hospital check entirely.
    marginal_weather_precip_pct: int = 30
    # Safety: no hospital within this radius + family + marginal weather → REJECTED.
    hospital_search_radius_miles: float = 30.0
    # Number of activity candidates shown to the LLM for ranking. More = more variety
    # but slightly slower (LLM reads the list). 20 is a good balance.
    max_candidate_activities: int = 20


class PathsConfig(BaseModel):
    base_dir: Path = Field(default_factory=lambda: Path.home() / ".nexus")
    plans_dir: Path | None = None
    feedback_dir: Path | None = None
    checkpoint_db: Path | None = None
    cache_dir: Path | None = None
    logs_dir: Path | None = None

    def model_post_init(self, __context: Any) -> None:  # noqa: ANN401
        if self.plans_dir is None:
            self.plans_dir = self.base_dir / "plans"
        if self.feedback_dir is None:
            self.feedback_dir = self.base_dir / "feedback"
        if self.checkpoint_db is None:
            self.checkpoint_db = self.base_dir / "checkpoints" / "nexus.db"
        if self.cache_dir is None:
            self.cache_dir = self.base_dir / "cache"
        if self.logs_dir is None:
            self.logs_dir = self.base_dir / "logs"

    @property
    def plans_dir_safe(self) -> Path:
        assert self.plans_dir is not None
        return self.plans_dir

    @property
    def cache_dir_safe(self) -> Path:
        assert self.cache_dir is not None
        return self.cache_dir

    @property
    def checkpoint_db_safe(self) -> Path:
        assert self.checkpoint_db is not None
        return self.checkpoint_db

    @property
    def checkpoints_dir(self) -> Path:
        """Parent directory of checkpoint_db (e.g. ~/.nexus/checkpoints)."""
        return self.checkpoint_db_safe.parent

    @property
    def logs_dir_safe(self) -> Path:
        assert self.logs_dir is not None
        return self.logs_dir


# ─────────────────────────────────────────────────────────────────────────────
# User/Family models (duplicated from schemas to avoid circular import)
# These are minimal stubs; full models live in nexus.state.schemas
# ─────────────────────────────────────────────────────────────────────────────


class _FamilyMemberConfig(BaseModel):
    name: str
    age: int
    interests: list[str] = Field(default_factory=list)
    comfort_distance_miles: float = 5.0
    requires_cell_service: bool = False


class _UserProfileConfig(BaseModel):
    name: str = "Alex"
    fitness_level: str = "intermediate"
    dietary_restrictions: list[str] = Field(default_factory=list)
    protein_target_g: int = 30
    max_driving_minutes: int = 90
    max_restaurant_radius_miles: float = 10.0
    home_address: str = ""
    home_coordinates: tuple[float, float] = (37.7749, -122.4194)
    preferred_activities: list[str] = Field(default_factory=list)


class _FamilyProfileConfig(BaseModel):
    vehicle_count: int = 1
    max_total_driving_minutes: int = 180
    members: list[_FamilyMemberConfig] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Root Config
# ─────────────────────────────────────────────────────────────────────────────


class NexusConfig(BaseModel):
    """
    Root configuration model. Loaded from ~/.nexus/profile.yaml + .env.

    Use NexusConfig.load() — do not construct directly in production.
    """

    user: _UserProfileConfig = Field(default_factory=_UserProfileConfig)
    family: _FamilyProfileConfig = Field(default_factory=_FamilyProfileConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    planning: PlanningConfig = Field(default_factory=PlanningConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    debug: bool = False  # Set by CLI --debug flag; not persisted to profile.yaml

    @classmethod
    def load(cls, profile_path: Path | None = None) -> NexusConfig:
        """
        Load configuration from profile.yaml + .env.

        Uses ruamel.yaml to preserve user-added comments on round-trip writes.
        """
        path = profile_path or Path.home() / ".nexus" / "profile.yaml"

        if not path.exists():
            raise FileNotFoundError(
                f"Profile not found at {path}. Run `nexus` and complete setup."
            )

        yaml = YAML()
        with open(path) as f:
            raw: dict = dict(yaml.load(f) or {})

        # Load API keys from .env alongside profile.yaml
        env_path = path.parent / ".env"
        if env_path.exists():
            api_keys = _parse_env(env_path)
            raw.setdefault("tools", {})
            if isinstance(raw["tools"], dict):
                raw["tools"].setdefault("api_keys", {}).update(api_keys)

        return cls(**raw)

    def save(self, profile_path: Path | None = None) -> None:
        """
        Write configuration back to profile.yaml.

        Uses ruamel.yaml to preserve existing comments and formatting.
        """
        path = profile_path or Path.home() / ".nexus" / "profile.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)

        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.default_flow_style = False

        # Exclude api_keys from profile.yaml — they live in .env
        data = self.model_dump(exclude={"tools": {"api_keys"}})
        # Convert Path objects to strings for YAML serialization
        data["paths"] = {
            k: str(v) for k, v in data["paths"].items() if v is not None
        }

        with open(path, "w") as f:
            yaml.dump(data, f)

    @classmethod
    def defaults(cls) -> NexusConfig:
        """Return a config with all defaults — useful for testing."""
        return cls()


def _parse_env(path: Path) -> dict[str, str]:
    """
    Parse a simple key=value .env file.

    Handles:
    - Comment lines (starting with #)
    - Quoted values (single or double)
    - Blank lines
    """
    keys: dict[str, str] = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                if key and value:
                    keys[key] = value
    except OSError:
        logger.warning("Could not read .env file at %s", path)
    return keys


def ensure_nexus_dirs(config: NexusConfig) -> None:
    """Create all required ~/.nexus/ subdirectories if they don't exist."""
    assert config.paths.plans_dir is not None
    assert config.paths.feedback_dir is not None
    assert config.paths.checkpoint_db is not None
    assert config.paths.cache_dir is not None
    assert config.paths.logs_dir is not None

    for directory in [
        config.paths.plans_dir,
        config.paths.feedback_dir,
        config.paths.checkpoint_db.parent,  # checkpoints/
        config.paths.cache_dir,
        config.paths.logs_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
