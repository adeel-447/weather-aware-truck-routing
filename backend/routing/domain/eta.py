"""Elapsed driving time along a route and checkpoint arrival instants.

ETAs are computed in UTC from an aware departure instant, so daylight-saving transitions cannot shift
them; local time is a display concern only. Driving time only: no rest, fuel or hours-of-service stops.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

EtaMethod = Literal["provider_segments", "proportional"]


@dataclass(frozen=True, slots=True)
class TimingCurve:
    """Monotonic (distance miles, elapsed seconds) knots, linearly interpolated between knots."""

    distances: tuple[float, ...]
    elapsed: tuple[float, ...]
    method: EtaMethod

    @classmethod
    def from_segments(cls, segments: Sequence[tuple[float, float]], total_miles: float) -> TimingCurve:
        """Build from consecutive (length miles, duration seconds) segments, e.g. HERE spans.

        Segment lengths are rescaled to ``total_miles`` so the curve uses the same distance basis as
        checkpoint sampling.
        """
        if not segments:
            raise ValueError("no segments")
        if any(length < 0 or duration < 0 for length, duration in segments):
            raise ValueError("segment length and duration must be non-negative")
        measured = sum(length for length, _ in segments)
        if measured <= 0:
            raise ValueError("segments have zero total length")
        scale = total_miles / measured
        distances, elapsed = [0.0], [0.0]
        for length, duration in segments:
            distances.append(distances[-1] + length * scale)
            elapsed.append(elapsed[-1] + duration)
        distances[-1] = total_miles
        return cls(tuple(distances), tuple(elapsed), "provider_segments")

    @classmethod
    def proportional(cls, total_miles: float, total_seconds: float) -> TimingCurve:
        """Fallback when the provider gives no segment timing: constant average speed."""
        if total_miles <= 0 or total_seconds < 0:
            raise ValueError("invalid route totals")
        return cls((0.0, total_miles), (0.0, total_seconds), "proportional")

    def elapsed_at(self, distance: float) -> float:
        if distance <= 0:
            return 0.0
        if distance >= self.distances[-1]:
            return self.elapsed[-1]
        # bisect_left: at a knot shared by a zero-length segment, use the earliest arrival.
        index = bisect_left(self.distances, distance)
        d0, d1 = self.distances[index - 1], self.distances[index]
        t0, t1 = self.elapsed[index - 1], self.elapsed[index]
        if d1 == d0:
            return t0
        return t0 + (t1 - t0) * (distance - d0) / (d1 - d0)


def arrival_at(departure: datetime, curve: TimingCurve, distance: float) -> datetime:
    if departure.tzinfo is None or departure.utcoffset() is None:
        raise ValueError("departure must be timezone-aware")
    return departure.astimezone(UTC) + timedelta(seconds=curve.elapsed_at(distance))
