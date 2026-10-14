"""Checkpoint distances and the representative interval each checkpoint stands for."""

from __future__ import annotations

from collections.abc import Sequence

ALLOWED_SPACINGS_MILES = (10, 25, 50)
# A final regular sample closer than this to the destination is merged into the destination.
ENDPOINT_EPSILON_MILES = 1e-6


def checkpoint_distances(total_miles: float, spacing_miles: float) -> list[float]:
    """0, S, 2S, ... plus the destination, each exactly once."""
    if total_miles <= 0:
        raise ValueError("route distance must be positive")
    if spacing_miles <= 0:
        raise ValueError("spacing must be positive")
    distances: list[float] = []
    step = 0
    while (distance := step * spacing_miles) < total_miles - ENDPOINT_EPSILON_MILES:
        distances.append(float(distance))
        step += 1
    distances.append(total_miles)
    return distances


def representative_intervals(distances: Sequence[float]) -> list[tuple[float, float]]:
    """Interval owned by each checkpoint: midpoint to previous neighbour through midpoint to next.

    The first starts at 0 and the last ends at the route total, so intervals partition the route.
    """
    if len(distances) < 2:
        raise ValueError("need origin and destination checkpoints")
    midpoints = [(a + b) / 2 for a, b in zip(distances, distances[1:], strict=False)]
    starts = [distances[0], *midpoints]
    ends = [*midpoints, distances[-1]]
    return list(zip(starts, ends, strict=True))
