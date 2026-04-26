"""
Open-Meteo weather provider — free, no API key required.

API docs: https://open-meteo.com/en/docs
Cache TTLs: weather 3h, AQI 1h, daylight 24h (static for a given day).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx

from nexus.tools.models import AirQuality, Coordinates, DaylightWindow, WeatherForecast

logger = logging.getLogger(__name__)

OPEN_METEO_BASE = "https://api.open-meteo.com/v1"
AIR_QUALITY_BASE = "https://air-quality-api.open-meteo.com/v1"
TIMEOUT = 10.0


class OpenMeteoWeather:
    """
    Weather provider using Open-Meteo free API.

    No API key required. Data is sourced from ECMWF and DWD.
    Rate limits: generous for non-commercial use.
    """

    async def get_forecast(
        self,
        coordinates: Coordinates,
        date: datetime,
    ) -> WeatherForecast:
        """Fetch weather forecast for given coordinates and datetime."""
        lat, lon = coordinates
        target_date = date.strftime("%Y-%m-%d")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{OPEN_METEO_BASE}/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "precipitation_probability_max,temperature_2m_max,weathercode",
                    "hourly": "lightning_potential",
                    "start_date": target_date,
                    "end_date": target_date,
                    "timezone": "auto",
                },
            )
            if resp.status_code == 400:
                # Date likely out of forecast range; return optimistic defaults
                logger.warning("meteorology: forecast API 400 for %s — using defaults", target_date)
                return WeatherForecast(
                    precipitation_probability=0.0,
                    lightning_risk=False,
                    conditions_text="Forecast unavailable (date out of range)",
                    temperature_high_f=65.0,
                    data_age_minutes=0,
                    confidence="estimated",
                )
            resp.raise_for_status()
            data = resp.json()

        daily = data.get("daily", {})
        precip_vals = daily.get("precipitation_probability_max", [None])
        temp_vals = daily.get("temperature_2m_max", [None])
        weathercode_vals = daily.get("weathercode", [0])

        precip = float(precip_vals[0] or 0)
        temp_c = float(temp_vals[0] or 20)
        temp_f = temp_c * 9 / 5 + 32
        weathercode = int(weathercode_vals[0] or 0)

        # Lightning heuristic: weathercodes 95-99 are thunderstorms
        lightning_risk = weathercode in range(95, 100)

        conditions_text = _weathercode_to_text(weathercode)

        return WeatherForecast(
            precipitation_probability=precip,
            lightning_risk=lightning_risk,
            conditions_text=conditions_text,
            temperature_high_f=temp_f,
            data_age_minutes=0,
            confidence="verified",
        )

    async def get_air_quality(
        self,
        coordinates: Coordinates,
    ) -> AirQuality:
        """Fetch current air quality index."""
        lat, lon = coordinates

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{AIR_QUALITY_BASE}/air-quality",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "us_aqi",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        current = data.get("current", {})
        aqi = int(current.get("us_aqi") or 0)

        return AirQuality(aqi=aqi, data_age_minutes=0, confidence="verified")

    async def get_daylight_window(
        self,
        coordinates: Coordinates,
        date: date,
    ) -> DaylightWindow:
        """Fetch sunrise/sunset times for a given date and location."""
        lat, lon = coordinates
        date_str = date.strftime("%Y-%m-%d")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{OPEN_METEO_BASE}/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "sunrise,sunset",
                    "start_date": date_str,
                    "end_date": date_str,
                    "timezone": "auto",
                },
            )
            if resp.status_code == 400:
                # Date out of forecast range; return astronomical approximation
                logger.warning(
                    "meteorology: daylight API 400 for %s — using 6am/8pm fallback", date_str
                )
                from datetime import time

                return DaylightWindow(
                    sunrise=datetime.combine(date, time(6, 0)),
                    sunset=datetime.combine(date, time(20, 0)),
                    confidence="estimated",
                )
            resp.raise_for_status()
            data = resp.json()

        daily = data.get("daily", {})
        sunrise_strs = daily.get("sunrise", [])
        sunset_strs = daily.get("sunset", [])

        # API returns ISO 8601 local time strings; utc_offset_seconds not used
        # (isoformat strings are parsed directly with tzinfo assignment below)

        def _parse(s: str) -> datetime:
            # "2026-04-19T06:30" -> datetime
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        sunrise = (
            _parse(sunrise_strs[0])
            if sunrise_strs
            else datetime.now(timezone.utc).replace(hour=6, minute=30)
        )
        sunset = (
            _parse(sunset_strs[0])
            if sunset_strs
            else datetime.now(timezone.utc).replace(hour=19, minute=45)
        )

        return DaylightWindow(
            sunrise=sunrise,
            sunset=sunset,
            data_age_minutes=0,
            confidence="verified",
        )


def _weathercode_to_text(code: int) -> str:
    """Convert WMO weather code to human-readable description."""
    _map = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Icy fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Heavy drizzle",
        61: "Light rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Light snow",
        73: "Moderate snow",
        75: "Heavy snow",
        80: "Light rain showers",
        81: "Moderate rain showers",
        82: "Heavy rain showers",
        95: "Thunderstorm",
        96: "Thunderstorm with hail",
        99: "Thunderstorm with heavy hail",
    }
    return _map.get(code, f"Weather code {code}")
