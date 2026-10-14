import pytest

from routing.domain.checkpoints import sample_positions
from routing.domain.geometry import cumulative_miles, haversine_miles, point_at_distance
from routing.domain.sampling import checkpoint_distances, representative_intervals
from routing.domain.units import lb_to_kg, meters_to_miles


def test_distances_include_origin_and_destination_once_when_not_divisible():
    assert checkpoint_distances(57.3, 25) == [0.0, 25.0, 50.0, 57.3]


def test_distances_when_divisible_do_not_duplicate_destination():
    assert checkpoint_distances(50.0, 25) == [0.0, 25.0, 50.0]
    assert checkpoint_distances(50.0 + 1e-9, 25) == [0.0, 25.0, 50.0 + 1e-9]


def test_route_shorter_than_spacing_has_exactly_two_checkpoints():
    assert checkpoint_distances(7.5, 10) == [0.0, 7.5]


@pytest.mark.parametrize("bad", [0, -1])
def test_distances_reject_non_positive(bad):
    with pytest.raises(ValueError):
        checkpoint_distances(bad, 10)
    with pytest.raises(ValueError):
        checkpoint_distances(10, bad)


@pytest.mark.parametrize(
    ("total", "spacing"), [(57.3, 25), (50.0, 25), (7.5, 10), (1234.56, 10), (99.99, 50)]
)
def test_intervals_partition_route(total, spacing):
    intervals = representative_intervals(checkpoint_distances(total, spacing))
    assert intervals[0][0] == 0.0
    assert intervals[-1][1] == total
    for (_, end), (start, _) in zip(intervals, intervals[1:], strict=False):
        assert end == start  # contiguous, no overlap or gap
    assert sum(end - start for start, end in intervals) == pytest.approx(total, abs=1e-6)


def test_interval_bounds_are_midpoints():
    assert representative_intervals([0.0, 25.0, 50.0, 57.3]) == [
        (0.0, 12.5),
        (12.5, 37.5),
        (37.5, 53.65),
        (53.65, 57.3),
    ]


def test_haversine_one_degree_latitude():
    assert haversine_miles((0.0, 0.0), (1.0, 0.0)) == pytest.approx(69.09, abs=0.01)


def test_cumulative_rescales_to_provider_total():
    points = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
    cumulative = cumulative_miles(points, total_miles=140.0)
    assert cumulative == pytest.approx([0.0, 70.0, 140.0])


def test_point_interpolated_along_polyline_not_straight_line():
    # L-shaped route: east then north. Straight-line interpolation would cut the corner.
    points = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0)]
    cumulative = cumulative_miles(points)
    lat, lon = point_at_distance(points, cumulative, cumulative[-1] * 0.75)
    assert lon == pytest.approx(1.0)
    assert lat == pytest.approx(0.5, abs=1e-3)


def test_sample_positions_start_and_end_on_route_endpoints():
    points = [(40.0, -100.0), (40.0, -99.0), (41.0, -99.0)]
    positions = sample_positions(points, total_miles=120.0, spacing_miles=50)
    assert [d for d, _ in positions] == [0.0, 50.0, 100.0, 120.0]
    assert positions[0][1] == points[0]
    assert positions[-1][1] == points[-1]


def test_unit_conversions():
    assert lb_to_kg(80_000) == 36_287
    assert lb_to_kg(30_000) == 13_608
    assert meters_to_miles(1609.344) == pytest.approx(1.0)
