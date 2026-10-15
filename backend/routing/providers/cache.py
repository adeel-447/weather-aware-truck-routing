"""Deduplicating, cached forecaster wrapper.

Locations are snapped to a fixed grid (``GRID_DEGREES`` ≈ 3–5 km) and the *full hourly series* for the
snapped point is cached, so a cached entry serves any instant inside it: caching never changes which
forecast hour a checkpoint ETA maps to. Keys include the current UTC hour because the provider window is
relative to "now".
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from routing.domain.forecast import HourlyForecast
from routing.domain.geometry import LatLon
from routing.providers.base import Forecaster, GeocodedPlace, Geocoder, ProviderRoute, TruckRouter

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
        self.description = inner.description
        self.fixed_window = inner.fixed_window
        self.cache = cache
        self.timeout_s = timeout_s
        self.now = now

    def hourly_forecasts(self, locations: Sequence[LatLon], forecast_hours: int) -> list[HourlyForecast]:
        hours = hours_bucket(forecast_hours)
        hour_key = self.now().strftime("%Y%m%d%H")
        # A fixed-window provider returns the same series whatever the horizon, so one entry serves
        # both route evaluation and the heatmap.
        window = "fixed" if self.fixed_window else str(hours)
        snapped = [snap(location) for location in locations]
        unique = list(dict.fromkeys(snapped))
        keys = {point: f"forecast:{hour_key}:{window}:{point[0]}:{point[1]}" for point in unique}

        found: dict[str, HourlyForecast] = self.cache.get_many(list(keys.values()))
        missing = [point for point in unique if keys[point] not in found]
        if missing:
            fetched = self.inner.hourly_forecasts(missing, hours)
            fresh = {keys[point]: forecast for point, forecast in zip(missing, fetched, strict=True)}
            # Empty series are failed lookups: use them for this request but never cache them.
            self.cache.set_many({k: f for k, f in fresh.items() if f.times}, timeout=self.timeout_s)
            found.update(fresh)
        return [found[keys[point]] for point in snapped]


GEOCODE_TIMEOUT_S = 24 * 60 * 60  # place coordinates do not change within a day


class CachedGeocoder:
    """Caches successful lookups by normalised query; misses are not cached."""

    def __init__(self, inner: Geocoder, cache: Any, timeout_s: int = GEOCODE_TIMEOUT_S) -> None:
        self.inner = inner
        self.cache = cache
        self.timeout_s = timeout_s

    def geocode(self, query: str) -> GeocodedPlace:
        digest = hashlib.sha256(" ".join(query.lower().split()).encode()).hexdigest()
        key = f"geocode:{digest}"
        found: GeocodedPlace | None = self.cache.get(key)
        if found is not None:
            return found
        place = self.inner.geocode(query)
        self.cache.set(key, place, timeout=self.timeout_s)
        return place


class CachedRouter:
    """Caches truck routes for an identical request (same points, departure, weight, alternatives)."""

    def __init__(self, inner: TruckRouter, cache: Any, timeout_s: int) -> None:
        self.inner = inner
        self.description = inner.description
        self.cache = cache
        self.timeout_s = timeout_s

    def truck_routes(
        self,
        origin: LatLon,
        destination: LatLon,
        departure: datetime,
        weight_kg: int,
        alternatives: int,
    ) -> list[ProviderRoute]:
        parts = (
            f"{origin[0]:.5f},{origin[1]:.5f}",
            f"{destination[0]:.5f},{destination[1]:.5f}",
            departure.astimezone(UTC).isoformat(),
            str(weight_kg),
            str(alternatives),
        )
        key = "route:" + hashlib.sha256("|".join(parts).encode()).hexdigest()
        found: list[ProviderRoute] | None = self.cache.get(key)
        if found is not None:
            return found
        routes = self.inner.truck_routes(origin, destination, departure, weight_kg, alternatives)
        self.cache.set(key, routes, timeout=self.timeout_s)
        return routes
