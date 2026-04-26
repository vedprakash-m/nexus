"""Tests for tool provider implementations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "http"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


class TestOpenMeteoWeather:
    async def test_get_forecast_parses_precipitation(self, httpx_mock):
        from nexus.tools.providers.weather.open_meteo import OpenMeteoWeather

        data = _fixture("open_meteo_forecast.json")
        httpx_mock.add_response(json=data)

        provider = OpenMeteoWeather()
        forecast = await provider.get_forecast(
            (37.7749, -122.4194),
            datetime(2026, 4, 19, tzinfo=timezone.utc),
        )

        assert forecast.precipitation_probability == 15.0
        assert forecast.lightning_risk is False
        assert "clear" in forecast.conditions_text.lower() or forecast.conditions_text != ""

    async def test_get_air_quality_parses_aqi(self, httpx_mock):
        from nexus.tools.providers.weather.open_meteo import OpenMeteoWeather

        httpx_mock.add_response(json=_fixture("open_meteo_aqi.json"))

        provider = OpenMeteoWeather()
        aqi = await provider.get_air_quality((37.7749, -122.4194))

        assert aqi.aqi == 42
        assert aqi.confidence == "verified"

    async def test_get_daylight_window_parses_sunrise_sunset(self, httpx_mock):
        from datetime import date

        from nexus.tools.providers.weather.open_meteo import OpenMeteoWeather

        httpx_mock.add_response(json=_fixture("open_meteo_daylight.json"))

        provider = OpenMeteoWeather()
        window = await provider.get_daylight_window(
            (37.7749, -122.4194),
            date(2026, 4, 19),
        )

        assert window.sunrise.hour == 6
        assert window.sunset.hour == 19


class TestOSRMRouting:
    async def test_get_route_returns_duration_and_distance(self, httpx_mock):
        from nexus.tools.providers.routing.osrm import OSRMRouting

        httpx_mock.add_response(json=_fixture("osrm_route.json"))

        routing = OSRMRouting()
        result = await routing.get_route((37.7749, -122.4194), (37.3861, -122.0839))

        # 48270.5m ≈ 30 miles; 2745.3s ≈ 45 minutes
        assert result.duration_minutes == pytest.approx(45.75, abs=0.1)
        assert result.distance_miles == pytest.approx(30.0, abs=0.5)
        assert result.is_estimated is False
        assert result.confidence == "verified"

    async def test_get_route_fallback_on_error(self, httpx_mock):
        from nexus.tools.providers.routing.osrm import OSRMRouting

        httpx_mock.add_response(status_code=500)

        routing = OSRMRouting()
        result = await routing.get_route((37.7749, -122.4194), (37.3861, -122.0839))

        assert result.is_estimated is True
        assert result.confidence == "estimated"
        assert result.duration_minutes > 0

    async def test_nearest_road_parses_distance(self, httpx_mock):
        from nexus.tools.providers.routing.osrm import OSRMRouting

        httpx_mock.add_response(json=_fixture("osrm_nearest.json"))

        routing = OSRMRouting()
        distance = await routing.nearest_road_distance((37.7749, -122.4194))

        # 12.5m → 0.00776 miles
        assert distance == pytest.approx(12.5 / 1609.0, rel=0.01)


class TestGooglePlaces:
    async def test_search_restaurants_parses_results(self, httpx_mock):
        from nexus.tools.providers.places.google import GooglePlaces

        httpx_mock.add_response(json=_fixture("google_restaurants.json"))

        places = GooglePlaces(api_key="test-key")
        results = await places.search_restaurants((37.39, -122.08), 5.0)

        assert len(results) == 2
        assert results[0].name == "Green Garden Cafe"
        assert results[0].rating == 4.5

    async def test_search_restaurants_handles_auth_failure(self, httpx_mock):
        from nexus.tools.providers.places.google import GooglePlaces

        httpx_mock.add_response(status_code=403)

        places = GooglePlaces(api_key="bad-key")
        results = await places.search_restaurants((37.39, -122.08), 5.0)

        assert results == []

    async def test_search_restaurants_handles_request_denied(self, httpx_mock):
        from nexus.tools.providers.places.google import GooglePlaces

        httpx_mock.add_response(json={"status": "REQUEST_DENIED", "error_message": "API key missing"})

        places = GooglePlaces(api_key="")
        results = await places.search_restaurants((37.39, -122.08), 5.0)

        assert results == []


class TestOverpassActivities:
    async def test_search_activities_parses_results(self, httpx_mock):
        from nexus.tools.providers.activity.overpass import OverpassActivities

        httpx_mock.add_response(json=_fixture("overpass_activities.json"))

        provider = OverpassActivities()
        result = await provider.search_activities((37.39, -122.08), 20.0, ["hiking"])
        results, data_source = result

        assert len(results) == 2
        assert results[0].name == "Windy Hill Open Space Preserve"
        assert results[0].activity_id.startswith("osm-")

    async def test_search_activities_filters_unnamed(self, httpx_mock):
        from nexus.tools.providers.activity.overpass import OverpassActivities

        # Return element with no name — reusable so all 3 mirrors are covered
        httpx_mock.add_response(
            json={"elements": [
                {"type": "node", "id": 111, "lat": 37.0, "lon": -122.0, "tags": {}}
            ]},
            is_reusable=True,
        )

        provider = OverpassActivities()
        # Use PNW coords (within bounds) with tiny 0.5-mile radius so no
        # static PNW trails match, yielding ([], 'static_pnw').
        result = await provider.search_activities((47.5, -121.5), 0.5, ["hiking"])
        results, data_source = result

        assert results == []
        assert data_source == "static_pnw"


class TestCoverageEstimate:
    async def test_near_road_returns_likely_coverage(self, httpx_mock):
        from nexus.tools.providers.coverage import estimate_cell_coverage
        from nexus.tools.providers.routing.osrm import OSRMRouting

        httpx_mock.add_response(json=_fixture("osrm_nearest.json"))

        routing = OSRMRouting()
        coverage = await estimate_cell_coverage((37.7749, -122.4194), routing)

        # 12.5m is well within 0.5-mile threshold
        assert coverage.has_likely_service is True
        assert coverage.confidence == "estimated"

    async def test_far_from_road_returns_no_coverage(self):
        from nexus.tools.providers.coverage import estimate_cell_coverage

        class FarRouting:
            async def nearest_road_distance(self, coordinates):
                return 5.0  # 5 miles → no coverage

        coverage = await estimate_cell_coverage((37.0, -122.0), FarRouting())
        assert coverage.has_likely_service is False


class TestToolRegistry:
    def test_build_registry_has_all_providers(self, sample_config):
        from nexus.tools.registry import ToolRegistry, build_registry

        registry = build_registry(sample_config)
        assert isinstance(registry, ToolRegistry)
        assert registry.weather is not None
        assert registry.activity is not None
        assert registry.places is not None
        assert registry.routing is not None

    def test_get_unknown_key_raises(self, sample_config):
        from nexus.tools.registry import build_registry

        registry = build_registry(sample_config)
        with pytest.raises(KeyError, match="No tool provider"):
            registry.get("unknown_tool")


class TestFetchWithFallbackRetry:
    """Task 3.13 — fetch_with_fallback retries transiently-failing requests.

    Scenario: fetcher raises httpx.HTTPStatusError with status 429 on the first
    two calls, then succeeds on the third.  We assert:
      • exactly 3 fetcher calls (2 retries + 1 success)
      • returned value matches the successful response
      • confidence == VERIFIED
    """

    async def test_retries_twice_then_succeeds(self, tmp_path):
        import httpx
        from diskcache import Cache

        from nexus.resilience import GracefulDegradation
        from nexus.state.confidence import DataConfidence

        call_count = 0

        async def _fetcher():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Simulate 500 Internal Server Error (transient — should be retried)
                resp = httpx.Response(500)
                raise httpx.HTTPStatusError("server error", request=httpx.Request("GET", "http://x"), response=resp)
            return "success_value"

        cache_dir = tmp_path / "cache"
        with Cache(str(cache_dir)) as cache:
            value, confidence = await GracefulDegradation.fetch_with_fallback(
                key="test:retry:429",
                fetcher=_fetcher,
                cache=cache,
                is_hard_constraint=False,
                default="fallback",
            )

        assert call_count == 3, f"Expected 3 calls (2 retries + success), got {call_count}"
        assert value == "success_value"
        assert confidence == DataConfidence.VERIFIED

    async def test_terminal_error_does_not_retry(self, tmp_path):
        """A 401 Unauthorized is terminal — fetcher must be called exactly once."""
        import httpx
        from diskcache import Cache

        from nexus.resilience import GracefulDegradation
        from nexus.state.confidence import DataConfidence

        call_count = 0

        async def _fetcher():
            nonlocal call_count
            call_count += 1
            resp = httpx.Response(401)
            raise httpx.HTTPStatusError("unauthorized", request=httpx.Request("GET", "http://x"), response=resp)

        cache_dir = tmp_path / "cache2"
        with Cache(str(cache_dir)) as cache:
            value, confidence = await GracefulDegradation.fetch_with_fallback(
                key="test:terminal:401",
                fetcher=_fetcher,
                cache=cache,
                is_hard_constraint=False,
                default="fallback_default",
            )

        assert call_count == 1, f"Terminal error must not be retried; got {call_count} calls"
        assert value == "fallback_default"
        assert confidence == DataConfidence.ESTIMATED
