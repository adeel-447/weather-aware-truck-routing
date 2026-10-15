"""Route polyline measurement and interpolation by cumulative distance."""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Sequence

EARTH_RADIUS_MILES = 3958.7613

LatLon = tuple[float, float]


def haversine_miles(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(min(1.0, h)))


def cumulative_miles(points: Sequence[LatLon], total_miles: float | None = None) -> list[float]:
    """Cumulative distance at each point.

    When ``total_miles`` (the provider's reported length) is given, distances are rescaled to it so
    sampling, ETA and mileage share the provider's distance basis. Polyline simplification makes the
    haversine sum differ slightly from the road length.
    """
    if len(points) < 2:
        raise ValueError("a route needs at least two points")
    cumulative = [0.0]
    for previous, current in zip(points, points[1:], strict=False):
        cumulative.append(cumulative[-1] + haversine_miles(previous, current))
    measured = cumulative[-1]
    if total_miles is not None and measured > 0:
        scale = total_miles / measured
        cumulative = [d * scale for d in cumulative]
        cumulative[-1] = total_miles
    return cumulative


def point_at_distance(points: Sequence[LatLon], cumulative: Sequence[float], distance: float) -> LatLon:
    """Position on the polyline at ``distance`` miles from its start (clamped to the route)."""
    if distance <= 0:
        return points[0]
    if distance >= cumulative[-1]:
        return points[-1]
    index = bisect_left(cumulative, distance)
    start, end = cumulative[index - 1], cumulative[index]
    fraction = 0.0 if end == start else (distance - start) / (end - start)
    (lat1, lon1), (lat2, lon2) = points[index - 1], points[index]
    return (lat1 + (lat2 - lat1) * fraction, lon1 + (lon2 - lon1) * fraction)


def simplify(points: Sequence[LatLon], tolerance_deg: float) -> list[LatLon]:
    """Douglas–Peucker simplification for display: keeps the endpoints and every point that deviates
    more than ``tolerance_deg`` from the simplified line. Distances use longitude scaled by
    cos(latitude) so the tolerance is roughly uniform on the ground.

    Only for drawing: sampling, ETAs and scoring always use the full geometry.
    """
    if len(points) < 3:
        return list(points)
    scale = math.cos(math.radians(sum(lat for lat, _ in points) / len(points)))

    def deviation(point: LatLon, start: LatLon, end: LatLon) -> float:
        py, px = point[0], point[1] * scale
        ay, ax = start[0], start[1] * scale
        by, bx = end[0], end[1] * scale
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        worst, worst_index = 0.0, -1
        for index in range(first + 1, last):
            distance = deviation(points[index], points[first], points[last])
            if distance > worst:
                worst, worst_index = distance, index
        if worst > tolerance_deg:
            keep[worst_index] = True
            stack.extend(((first, worst_index), (worst_index, last)))
    return [point for point, kept in zip(points, keep, strict=True) if kept]
