"""Provider-neutral interfaces and result types. Adapters translate provider payloads into these."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from routing.domain.forecast import HourlyForecast
from routing.domain.geometry import LatLon


@dataclass(frozen=True, slots=True)
class GeocodedPlace:
    label: str
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    route_id: str
    points: list[LatLon]
    distance_miles: float
    duration_seconds: float
    # Consecutive (length miles, duration seconds) segments along the route, or None when the provider
    # gave no usable segment timing (the proportional ETA fallback is used and disclosed).
    timing_segments: list[tuple[float, float]] | None
    notices: list[str] = field(default_factory=list)


class Geocoder(Protocol):
    def geocode(self, query: str) -> GeocodedPlace: ...


class TruckRouter(Protocol):
    def truck_routes(
        self,
        origin: LatLon,
        destination: LatLon,
        departure: datetime,
        weight_kg: int,
        alternatives: int,
    ) -> list[ProviderRoute]: ...


class Forecaster(Protocol):
    def hourly_forecasts(self, locations: Sequence[LatLon], forecast_hours: int) -> list[HourlyForecast]:
        """One hourly series per location, in input order, starting shortly before the current hour."""
        ...
