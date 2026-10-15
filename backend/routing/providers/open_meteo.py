"""Open-Meteo hourly forecast adapter.

Verified against docs and a live response (2026-10-14): ``wind_speed_unit=mph`` returns "mp/h";
``precipitation_unit=inch`` returns rain, showers and snowfall in "inch"; multiple coordinates return a
JSON list (a single coordinate returns an object); ``forecast_hours`` counts from the current hour and is
capped at 384; trailing hours may be null.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from routing.domain.forecast import HourlyForecast
from routing.domain.geometry import LatLon
from routing.providers.errors import ProviderError
from routing.providers.http import JsonClient

PROVIDER = "Open-Meteo"
MAX_FORECAST_HOURS = 384
PAST_HOURS = 2  # covers departures slightly in the past and the first preceding-hour bucket
LOCATIONS_PER_REQUEST = 100
HOURLY_VARIABLES = ("wind_speed_10m", "rain", "showers", "snowfall")
EXPECTED_UNITS = {"wind_speed_10m": "mp/h", "rain": "inch", "showers": "inch", "snowfall": "inch"}


class OpenMeteoForecaster:
    description = "Open-Meteo hourly forecast"

    def __init__(self, client: JsonClient, base_url: str, api_key: str = "") -> None:
        self.client = client
        self.base_url = base_url
        self.api_key = api_key

    def hourly_forecasts(self, locations: Sequence[LatLon], forecast_hours: int) -> list[HourlyForecast]:
        hours = max(1, min(forecast_hours, MAX_FORECAST_HOURS))
        results: list[HourlyForecast] = []
        for start in range(0, len(locations), LOCATIONS_PER_REQUEST):
            chunk = locations[start : start + LOCATIONS_PER_REQUEST]
            body = self.client.get(self.base_url, self._params(chunk, hours))
            payloads = body if isinstance(body, list) else [body]
            if len(payloads) != len(chunk):
                raise ProviderError(PROVIDER, "response location count does not match request")
            results.extend(_parse(payload) for payload in payloads)
        return results

    def _params(self, chunk: Sequence[LatLon], hours: int) -> dict[str, str | int]:
        params: dict[str, str | int] = {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in chunk),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in chunk),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "timeformat": "unixtime",
            "past_hours": PAST_HOURS,
            "forecast_hours": hours,
        }
        if self.api_key:
            params["apikey"] = self.api_key
        return params


def _parse(payload: Any) -> HourlyForecast:
    if not isinstance(payload, dict) or payload.get("error"):
        reason = payload.get("reason") if isinstance(payload, dict) else None
        raise ProviderError(PROVIDER, reason or "unexpected forecast response")
    try:
        units = payload["hourly_units"]
        for variable, unit in EXPECTED_UNITS.items():
            if units.get(variable) != unit:
                raise ProviderError(PROVIDER, f"unexpected unit for {variable}: {units.get(variable)!r}")
        hourly = payload["hourly"]
        times = tuple(datetime.fromtimestamp(int(t), UTC) for t in hourly["time"])
        rain = tuple(
            None if r is None or s is None else float(r) + float(s)
            for r, s in zip(hourly["rain"], hourly["showers"], strict=True)
        )
        return HourlyForecast(
            times=times,
            wind_mph=tuple(_float_or_none(v) for v in hourly["wind_speed_10m"]),
            rain_in_hr=rain,
            snow_in_hr=tuple(_float_or_none(v) for v in hourly["snowfall"]),
        )
    except ProviderError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError(PROVIDER, "unexpected forecast response") from exc


def _float_or_none(value: Any) -> float | None:
    return None if value is None else float(value)
