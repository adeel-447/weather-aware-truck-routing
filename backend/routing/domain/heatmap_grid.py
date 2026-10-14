"""Bounded grid of cells covering the trip corridor, for the forecast heatmap.

Every corridor point marks its cell plus a one-cell ring around it. The cell size starts fine and doubles
until the grid fits ``max_cells``, so long trips get coarser cells instead of more forecast requests.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from routing.domain.geometry import LatLon

MAX_CELLS = 300
INITIAL_CELL_DEGREES = 0.1
MIN_CELLS = 9  # one cell plus its ring: any corridor fits once cells are large enough


@dataclass(frozen=True, slots=True)
class CorridorGrid:
    cell_degrees: float
    centers: tuple[LatLon, ...]  # sorted by (lat, lon) for deterministic output


def _cells(corridor: Sequence[LatLon], size: float) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for lat, lon in corridor:
        # Offset to non-negative indices so one large enough cell holds every point.
        i, j = math.floor((lat + 90) / size), math.floor((lon + 180) / size)
        cells.update((i + di, j + dj) for di in (-1, 0, 1) for dj in (-1, 0, 1))
    return cells


def corridor_grid(
    corridor: Sequence[LatLon],
    max_cells: int = MAX_CELLS,
    initial_degrees: float = INITIAL_CELL_DEGREES,
) -> CorridorGrid:
    if not corridor:
        raise ValueError("corridor is empty")
    if max_cells < MIN_CELLS:
        raise ValueError(f"max_cells must be at least {MIN_CELLS}")
    size = initial_degrees
    cells = _cells(corridor, size)
    # Terminates: at >= 360 degrees every point shares one cell, i.e. 9 cells with its ring.
    while len(cells) > max_cells:
        size *= 2
        cells = _cells(corridor, size)
    centers = tuple(
        sorted((round((i + 0.5) * size - 90, 4), round((j + 0.5) * size - 180, 4)) for i, j in cells)
    )
    return CorridorGrid(cell_degrees=size, centers=centers)
