"""Deduplicating, cached forecaster wrapper.

Locations are snapped to a fixed grid (``GRID_DEGREES`` ≈ 3–5 km) and the *full hourly series* for the
snapped point is cached, so a cached entry serves any instant inside it: caching never changes which
forecast hour a checkpoint ETA maps to. Keys include the current UTC hour because the provider window is
relative to "now".
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from routing.domain.forecast import HourlyForecast
from routing.domain.geometry import LatLon
from routing.providers.base import Forecaster

GRID_DEGREES = 0.05
HOUR_BUCKETS = (72, 168, 384)


def snap(location: LatLon) -> LatLon:
    lat, lon = location
    return (
        round(round(lat / GRID_DEGREES) * GRID_DEGREES, 4),
        round(round(lon / GRID_DEGREES) * GRID_DEGREES, 4),
    )


def hours_bucket(forecast_hours: int) -> int:
    return next((b for b in HOUR_BUCKETS if forecast_hours <= b), HOUR_BUCKETS[-1])


class CachedForecaster:
    def __init__(
        self,
        inner: Forecaster,
        cache: Any,
        timeout_s: int,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.inner = inner
        self.cache = cache
        self.timeout_s = timeout_s
        self.now = now

    def hourly_forecasts(self, locations: Sequence[LatLon], forecast_hours: int) -> list[HourlyForecast]:
        hours = hours_bucket(forecast_hours)
        hour_key = self.now().strftime("%Y%m%d%H")
        snapped = [snap(location) for location in locations]
        unique = list(dict.fromkeys(snapped))
        keys = {point: f"forecast:{hour_key}:{hours}:{point[0]}:{point[1]}" for point in unique}

        found: dict[str, HourlyForecast] = self.cache.get_many(list(keys.values()))
        missing = [point for point in unique if keys[point] not in found]
        if missing:
            fetched = self.inner.hourly_forecasts(missing, hours)
            fresh = {keys[point]: forecast for point, forecast in zip(missing, fetched, strict=True)}
            self.cache.set_many(fresh, timeout=self.timeout_s)
            found.update(fresh)
        return [found[keys[point]] for point in snapped]
