"""Selecting forecast values at an arbitrary instant from an hourly series.

Semantics follow Open-Meteo's documented conventions:
- wind speed is instantaneous at each hour, so it is linearly interpolated between bracketing hours;
- rain and snowfall are totals over the *preceding* hour, so the bucket whose window contains the
  instant is used (the first timestamp >= instant), never interpolated.
Instants outside the covered window yield ``None`` (unavailable), never a substitute value.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from routing.domain.types import WeatherSample

HOUR = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class HourlyForecast:
    """Hourly series for one location. ``times`` are UTC, strictly increasing and one hour apart.

    ``rain_in_hr`` is total liquid precipitation for the preceding hour (adapter combines rain + showers).
    """

    times: tuple[datetime, ...]
    wind_mph: tuple[float | None, ...]
    rain_in_hr: tuple[float | None, ...]
    snow_in_hr: tuple[float | None, ...]

    def __post_init__(self) -> None:
        n = len(self.times)
        if not (len(self.wind_mph) == len(self.rain_in_hr) == len(self.snow_in_hr) == n):
            raise ValueError("forecast series lengths differ")
        if any(t.tzinfo is None for t in self.times):
            raise ValueError("forecast times must be timezone-aware")
        if any(b - a != HOUR for a, b in zip(self.times, self.times[1:], strict=False)):
            raise ValueError("forecast times must be consecutive hours")


def _instantaneous(times: Sequence[datetime], values: Sequence[float | None], at: datetime) -> float | None:
    if not times or at < times[0] or at > times[-1]:
        return None
    index = bisect_left(times, at)
    if times[index] == at:
        return values[index]
    before, after = values[index - 1], values[index]
    if before is None or after is None:
        return None
    fraction = (at - times[index - 1]) / HOUR
    return before + (after - before) * fraction


def _preceding_hour_bucket(
    times: Sequence[datetime], values: Sequence[float | None], at: datetime
) -> float | None:
    if not times or at <= times[0] - HOUR or at > times[-1]:
        return None
    return values[bisect_left(times, at)]


def weather_at(forecast: HourlyForecast, at: datetime) -> WeatherSample:
    instant = at.astimezone(UTC)
    return WeatherSample(
        wind_mph=_instantaneous(forecast.times, forecast.wind_mph, instant),
        rain_in_hr=_preceding_hour_bucket(forecast.times, forecast.rain_in_hr, instant),
        snow_in_hr=_preceding_hour_bucket(forecast.times, forecast.snow_in_hr, instant),
    )
