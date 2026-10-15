"""Build ETA-aligned, risk-classified checkpoints for one route."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from routing.domain.eta import TimingCurve, arrival_at
from routing.domain.geometry import LatLon, cumulative_miles, point_at_distance
from routing.domain.risk import assess
from routing.domain.sampling import checkpoint_distances, representative_intervals
from routing.domain.types import Checkpoint, WeatherSample

# (lat, lon, arrival instant in UTC) -> weather at that place and time.
WeatherLookup = Callable[[float, float, datetime], WeatherSample]


def sample_positions(
    points: Sequence[LatLon],
    total_miles: float,
    spacing_miles: float,
    cumulative: Sequence[float] | None = None,
) -> list[tuple[float, LatLon]]:
    """(distance, position) for each checkpoint, interpolated along the route polyline.

    Pass ``cumulative`` (from :func:`cumulative_miles`) to reuse it when sampling a route twice.
    """
    if cumulative is None:
        cumulative = cumulative_miles(points, total_miles)
    return [
        (d, point_at_distance(points, cumulative, d))
        for d in checkpoint_distances(total_miles, spacing_miles)
    ]


def build_checkpoints(
    positions: Sequence[tuple[float, LatLon]],
    departure: datetime,
    timing: TimingCurve,
    weather_lookup: WeatherLookup,
    load_lb: float,
) -> list[Checkpoint]:
    """Checkpoints for positions from :func:`sample_positions` (computed once per route by the caller)."""
    intervals = representative_intervals([d for d, _ in positions])
    checkpoints = []
    for (distance, (lat, lon)), (start, end) in zip(positions, intervals, strict=True):
        eta = arrival_at(departure, timing, distance)
        weather = weather_lookup(lat, lon, eta)
        checkpoints.append(
            Checkpoint(
                distance_miles=distance,
                lat=lat,
                lon=lon,
                eta=eta,
                weather=weather,
                risk=assess(weather, load_lb),
                interval_start_miles=start,
                interval_end_miles=end,
            )
        )
    return checkpoints
