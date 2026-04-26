"""
ToolRegistry — central registry for all tool provider instances.

Agents call registry.get("weather") instead of importing providers directly.
This enables easy mocking in tests and runtime provider switching.

Provider mapping (tasks.md §3.13):
    "weather"  → OpenMeteoWeather
    "activity" → OverpassActivities
    "places"   → GooglePlaces
    "routing"  → OSRMRouting
"""

from __future__ import annotations

from typing import TypeVar, overload

from nexus.tools.interfaces import ActivityTool, PlacesTool, RoutingTool, WeatherTool

# All supported tool types
_TOOL_KEY = str
_PROVIDERS: dict[str, object] = {}

T = TypeVar("T")


class ToolRegistry:
    """
    Runtime registry of initialized tool providers.

    Created once at startup (in graph.py) and passed to all agents via
    WeekendPlanState["tool_registry"].

    Usage:
        registry.get("weather")   → WeatherTool instance
        registry.get("activity")  → ActivityTool instance
        registry.get("places")    → PlacesTool instance
        registry.get("routing")   → RoutingTool instance
    """

    def __init__(self) -> None:
        self._providers: dict[str, object] = {}

    def register(self, name: str, provider: object) -> None:
        """Register a provider under the given name."""
        self._providers[name] = provider

    def get(self, name: str) -> object:
        """
        Retrieve a registered provider by name.

        Raises KeyError if the provider hasn't been registered.
        """
        try:
            return self._providers[name]
        except KeyError as exc:
            raise KeyError(
                f"No tool provider registered for '{name}'. "
                f"Available: {list(self._providers.keys())}"
            ) from exc

    @property
    def weather(self) -> WeatherTool:
        """Type-safe accessor for weather provider."""
        return self._providers["weather"]  # type: ignore[return-value]

    @property
    def activity(self) -> ActivityTool:
        """Type-safe accessor for activity provider."""
        return self._providers["activity"]  # type: ignore[return-value]

    @property
    def places(self) -> PlacesTool:
        """Type-safe accessor for places provider."""
        return self._providers["places"]  # type: ignore[return-value]

    @property
    def routing(self) -> RoutingTool:
        """Type-safe accessor for routing provider."""
        return self._providers["routing"]  # type: ignore[return-value]

    def __repr__(self) -> str:
        return f"ToolRegistry(providers={list(self._providers.keys())})"


def build_registry(config: object) -> ToolRegistry:
    """
    Build a ToolRegistry from a NexusConfig.

    Provider map (tasks.md §3.13):
        weather  → OpenMeteoWeather (no key needed)
        activity → OverpassActivities (no key needed)
        places   → GooglePlaces (GOOGLE_PLACES_API_KEY required)
        routing  → OSRMRouting (no key needed)
    """
    from nexus.config import NexusConfig
    from nexus.tools.providers.activity.overpass import OverpassActivities
    from nexus.tools.providers.places.google import GooglePlaces
    from nexus.tools.providers.routing.osrm import OSRMRouting
    from nexus.tools.providers.weather.open_meteo import OpenMeteoWeather

    assert isinstance(config, NexusConfig)

    from diskcache import Cache
    _activity_cache = Cache(str(config.paths.cache_dir_safe / "activity"))

    registry = ToolRegistry()
    registry.register("weather", OpenMeteoWeather())
    registry.register("activity", OverpassActivities(cache=_activity_cache))
    registry.register(
        "places",
        GooglePlaces(api_key=config.tools.api_keys.get("GOOGLE_PLACES_API_KEY", "")),
    )
    registry.register("routing", OSRMRouting())
    return registry
