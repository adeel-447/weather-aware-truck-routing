"""HERE Destination Weather API v3 hourly forecast adapter.

Verified against the v3 OpenAPI spec and a live response (2026-10-15):
- ``GET /v3/report?products=forecastHourly&location={lat},{lng}&units=imperial`` returns
  ``places[0].hourlyForecasts[0].forecasts[]``: 168 consecutive hours from the current hour.
- Each item has ``time`` as local ISO-8601 with offset (converted to UTC here), ``windSpeed`` in mph
  and ``rainFall`` / ``snowFall`` in inches (with ``units=imperial``).
- One location per request; there is no batch parameter, so locations are fetched in parallel.

The docs do not say whether an hourly ``rainFall`` / ``snowFall`` value covers the hour before or
after its timestamp. The domain reads precipitation from the first timestamp >= ETA, so each bucket
here is set to the larger of its own and the previous hour's value: risk can only be overstated,
never understated, under either convention.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from typing import Any

from routing.domain.forecast import HourlyForecast
from routing.domain.geometry import LatLon
from routing.providers.errors import ProviderConfigError, ProviderError, ProviderTimeout
from routing.providers.http import JsonClient

logger = logging.getLogger(__name__)

PROVIDER = "HERE"
EMPTY = HourlyForecast(times=(), wind_mph=(), rain_in_hr=(), snow_in_hr=())


class HereWeatherForecaster:
    description = "HERE Destination Weather hourly forecast"
    fixed_window = True  # always the full 168-hour series

    def __init__(
        self,
        client: JsonClient,
        base_url: str,
        api_key: str,
        concurrency: int,
        deadline_s: float = 60.0,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.concurrency = max(1, concurrency)
        # Overall limit for one batch; each call also has the HTTP client's own budget.
        self.deadline_s = deadline_s

    def hourly_forecasts(self, locations: Sequence[LatLon], forecast_hours: int) -> list[HourlyForecast]:
        """``forecast_hours`` is ignored: HERE always returns its full 168-hour series."""
        if not self.api_key:
            raise ProviderConfigError(PROVIDER, "HERE_API_KEY is not configured")
        if not locations:
            return []
        pool = ThreadPoolExecutor(max_workers=min(self.concurrency, len(locations)))
        futures: list[Future[HourlyForecast | ProviderError]] = [
            pool.submit(self._fetch, location) for location in locations
        ]
        wait(futures, timeout=self.deadline_s)
        # Do not wait for stragglers: queued lookups are cancelled, running ones end within their own
        # HTTP budget in the background.
        pool.shutdown(wait=False, cancel_futures=True)
        late = ProviderTimeout(PROVIDER, f"weather lookups exceeded {self.deadline_s:.0f} s")
        outcomes = [
            future.result() if future.done() and not future.cancelled() else late for future in futures
        ]

        failures = [outcome for outcome in outcomes if isinstance(outcome, ProviderError)]
        if len(failures) == len(outcomes):
            raise failures[0]  # nothing usable: report the provider error instead of all-Unknown
        if failures:
            logger.warning("%s weather: %d of %d locations failed", PROVIDER, len(failures), len(outcomes))
        # A failed location becomes an empty series: its checkpoints are Unknown, never Low.
        return [EMPTY if isinstance(outcome, ProviderError) else outcome for outcome in outcomes]

    def _fetch(self, location: LatLon) -> HourlyForecast | ProviderError:
        lat, lon = location
        params: dict[str, str | int] = {
            "products": "forecastHourly",
            "location": f"{lat:.4f},{lon:.4f}",
            "units": "imperial",
            "apiKey": self.api_key,
        }
        try:
            return parse_hourly(self.client.get(f"{self.base_url}/report", params))
        except ProviderError as exc:
            return exc


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _conservative(values: list[float | None]) -> tuple[float | None, ...]:
    """Each bucket becomes max(previous hour, this hour); unknown stays unknown."""
    result: list[float | None] = []
    for index, value in enumerate(values):
        previous = values[index - 1] if index > 0 else value
        result.append(None if value is None or previous is None else max(value, previous))
    return tuple(result)


def parse_hourly(body: Any) -> HourlyForecast:
    try:
        items = body["places"][0]["hourlyForecasts"][0]["forecasts"]
        times = tuple(datetime.fromisoformat(item["time"]).astimezone(UTC) for item in items)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError(PROVIDER, "unexpected weather response") from exc
    if any(time.tzinfo is None for time in times):
        raise ProviderError(PROVIDER, "weather times lack a UTC offset")
    try:
        return HourlyForecast(
            times=times,
            wind_mph=tuple(_number(item.get("windSpeed")) for item in items),
            rain_in_hr=_conservative([_number(item.get("rainFall")) for item in items]),
            snow_in_hr=_conservative([_number(item.get("snowFall")) for item in items]),
        )
    except ValueError as exc:  # e.g. hours not consecutive
        raise ProviderError(PROVIDER, f"unexpected weather series: {exc}") from exc
