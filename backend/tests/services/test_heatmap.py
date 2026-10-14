from datetime import UTC, datetime, timedelta

import pytest

from routing.domain.heatmap_grid import MAX_CELLS, corridor_grid
from routing.services.heatmap import corridor_heatmap
from tests.fakes import FakeForecaster

REFERENCE = datetime(2026, 10, 20, 13, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 20, 12, 30, tzinfo=UTC)
SHORT = [(41.88, -87.63), (42.27, -89.09)]


def test_single_point_grid_is_cell_plus_ring():
    grid = corridor_grid([(41.88, -87.63)])
    assert grid.cell_degrees == 0.1
    assert len(grid.centers) == 9


def test_long_corridor_coarsens_until_bounded():
    # Coast-to-coast-like corridor, one point every ~0.05 degrees.
    corridor = [(34.0 + i * 0.006, -118.0 + i * 0.05) for i in range(1000)]
    grid = corridor_grid(corridor)
    assert len(grid.centers) <= MAX_CELLS
    assert grid.cell_degrees > 0.1
    assert grid == corridor_grid(list(reversed(corridor)))  # deterministic


def test_any_corridor_fits_a_small_cap_by_coarsening():
    corridor = [(25.0 + i * 0.02, -124.0 + i * 0.06) for i in range(1000)]  # continental span
    grid = corridor_grid(corridor, max_cells=9)
    assert len(grid.centers) <= 9


def test_corridor_crossing_equator_and_prime_meridian_terminates():
    grid = corridor_grid([(-1.0, -1.0), (1.0, 1.0)], max_cells=9)
    assert len(grid.centers) <= 9


def test_cell_centers_contain_their_corridor_point():
    grid = corridor_grid([(41.88, -87.63)])
    lat, lon = grid.centers[4]  # middle of the 3x3 block
    half = grid.cell_degrees / 2
    assert abs(lat - 41.88) <= half and abs(lon + 87.63) <= half


def test_invalid_grid_inputs_are_rejected():
    with pytest.raises(ValueError):
        corridor_grid([])
    with pytest.raises(ValueError):
        corridor_grid([(41.0, -87.0)], max_cells=8)


def test_heatmap_has_49_hourly_frames_from_reference_with_one_forecast_call():
    forecaster = FakeForecaster()
    result = corridor_heatmap(SHORT, REFERENCE + timedelta(minutes=25), 20_000, forecaster, now=NOW)
    assert result["reference_at"] == "2026-10-20T13:00:00Z"
    assert len(result["frames"]) == 49
    assert result["frames"][0]["valid_at"] == "2026-10-20T13:00:00Z"
    assert result["frames"][48]["valid_at"] == "2026-10-22T13:00:00Z"
    assert len(forecaster.calls) == 1
    assert forecaster.calls[0][1] == 50  # reference + 48 h is 48.5 h after now -> 49 + 1
    cells = len(result["cells"])
    assert all(len(frame["severity"]) == cells for frame in result["frames"])
    assert "not the weather at each checkpoint's ETA" in result["note"]


def test_heatmap_frames_follow_valid_time_and_apply_load_rules():
    def weather(lat, lon, at):
        return (47.0 if at >= REFERENCE + timedelta(hours=10) else 5.0, 0.0, 0.0)

    light = corridor_heatmap(SHORT, REFERENCE, 30_000, FakeForecaster(weather), now=NOW)
    heavy = corridor_heatmap(SHORT, REFERENCE, 30_001, FakeForecaster(weather), now=NOW)
    assert set(light["frames"][0]["severity"]) == {0}
    assert set(light["frames"][10]["severity"]) == {3}  # 47 mph -> Severe
    assert set(heavy["frames"][10]["severity"]) == {4}  # >30,000 lb -> No Travel


def test_frames_beyond_forecast_are_unavailable_not_low():
    forecaster = FakeForecaster(start=REFERENCE - timedelta(hours=2), hours=12)
    result = corridor_heatmap(SHORT, REFERENCE, 20_000, forecaster, now=NOW)
    assert result["frames"][5]["available"] is True
    assert result["frames"][20]["available"] is False
    assert set(result["frames"][20]["severity"]) == {None}


def test_heatmap_window_counts_from_current_hour():
    # now 12:30, reference 13:00: the last frame (+48 h = 13:00 two days later) must be covered.
    forecaster = FakeForecaster()
    corridor_heatmap(SHORT, REFERENCE, 20_000, forecaster, now=NOW)
    window_start = NOW.replace(minute=0)
    hours = forecaster.calls[0][1]
    assert window_start + timedelta(hours=hours - 1) >= REFERENCE + timedelta(hours=48)


def test_default_cell_cap_matches_configured_default():
    from django.conf import settings

    assert MAX_CELLS == settings.HEATMAP_MAX_CELLS == 200
