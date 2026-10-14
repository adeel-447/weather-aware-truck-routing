"""Normalized domain types shared by risk, sampling, ETA and ranking logic.

Units are fixed throughout the domain layer: miles, seconds, mph, inches/hour, pounds, UTC instants.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class Severity(IntEnum):
    """Ordered risk levels. The integer value is the numeric score used for the weighted average."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True, slots=True)
class WeatherSample:
    """Weather at one place and instant. ``None`` means the value is unavailable, never zero."""

    wind_mph: float | None
    rain_in_hr: float | None
    snow_in_hr: float | None

    @property
    def is_complete(self) -> bool:
        return None not in (self.wind_mph, self.rain_in_hr, self.snow_in_hr)


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """Final checkpoint risk. ``severity is None`` means unknown (incomplete weather)."""

    severity: Severity | None
    factors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Checkpoint:
    distance_miles: float
    lat: float
    lon: float
    eta: datetime
    weather: WeatherSample
    risk: RiskAssessment
    interval_start_miles: float
    interval_end_miles: float

    @property
    def interval_miles(self) -> float:
        return self.interval_end_miles - self.interval_start_miles


@dataclass(frozen=True, slots=True)
class SeveritySummary:
    """Mileage accounting for one route. ``miles`` holds known-severity miles; unknown is separate."""

    miles: dict[Severity, float]
    unknown_miles: float
    total_miles: float
    weighted_average_risk: float | None

    @property
    def known_miles(self) -> float:
        return sum(self.miles.values())

    @property
    def has_no_travel(self) -> bool:
        return self.miles[Severity.NO_TRAVEL] > 0

    @property
    def is_verified(self) -> bool:
        return self.unknown_miles == 0
