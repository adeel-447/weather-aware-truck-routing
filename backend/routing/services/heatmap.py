"""Corridor forecast heatmap: composite risk for a bounded grid at 49 hourly valid times.

Independent of ETA-based route scoring: every cell is evaluated at the same valid time (reference + offset).
One batched (and cached) forecast request covers all cells and all frames, so the client can scrub the
slider without further requests.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from routing.domain.forecast import forecast_hours_needed, weather_at
from routing.domain.geometry import LatLon
from routing.domain.heatmap_grid import MAX_CELLS, corridor_grid
from routing.domain.risk import assess
from routing.providers.base import Forecaster
from routing.services.payloads import HeatmapFramePayload, HeatmapPayload, UnitsPayload
from routing.services.serialization import iso_utc, round_or_none

MAX_OFFSET_HOURS = 48
UNITS: UnitsPayload = {"wind_mph": "mph", "rain_in_hr": "in/hr", "snow_in_hr": "in/hr"}
NOTE = (
    "Forecast conditions across the corridor at the selected valid time, using the same risk rules and "
    "cargo load as route scoring. This is not the weather at each checkpoint's ETA and does not affect "
    "the route recommendation."
)


def corridor_heatmap(
    corridor: Sequence[LatLon],
    reference_at: datetime,
    load_lb: float,
    forecaster: Forecaster,
    now: datetime | None = None,
    max_cells: int = MAX_CELLS,
) -> HeatmapPayload:
    now = now or datetime.now(UTC)
    reference = reference_at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    grid = corridor_grid(corridor, max_cells=max_cells)
    last_valid = reference + timedelta(hours=MAX_OFFSET_HOURS)
    series = forecaster.hourly_forecasts(list(grid.centers), forecast_hours_needed(last_valid, now))

    frames: list[HeatmapFramePayload] = []
    for offset in range(MAX_OFFSET_HOURS + 1):
        valid_at = reference + timedelta(hours=offset)
        samples = [weather_at(forecast, valid_at) for forecast in series]
        severities = [assess(sample, load_lb).severity for sample in samples]
        frames.append(
            {
                "offset_hours": offset,
                "valid_at": iso_utc(valid_at),
                "available": any(s is not None for s in severities),
                "severity": [s.value if s is not None else None for s in severities],
                "wind_mph": [round_or_none(s.wind_mph, 1) for s in samples],
                "rain_in_hr": [round_or_none(s.rain_in_hr, 3) for s in samples],
                "snow_in_hr": [round_or_none(s.snow_in_hr, 3) for s in samples],
            }
        )

    return {
        "layer": "composite_severity",
        "severity_scale": {"0": "low", "1": "moderate", "2": "high", "3": "severe", "4": "no_travel"},
        "units": UNITS,
        "note": NOTE,
        "reference_at": iso_utc(reference),
        "load_weight_lb": load_lb,
        "cell_size_degrees": grid.cell_degrees,
        "cells": [[lon, lat] for lat, lon in grid.centers],
        "frames": frames,
        "generated_at": iso_utc(now),
    }
