from datetime import UTC, datetime, timedelta

import pytest

from routing.domain.checkpoints import build_checkpoints
from routing.domain.eta import TimingCurve
from routing.domain.ranking import RecommendationStatus, RouteScore, RouteStanding, recommend
from routing.domain.scoring import summarize
from routing.domain.types import Severity, SeveritySummary, WeatherSample

L, M, H, S, NT = Severity.LOW, Severity.MODERATE, Severity.HIGH, Severity.SEVERE, Severity.NO_TRAVEL
DEPARTURE = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
CALM = WeatherSample(wind_mph=5.0, rain_in_hr=0.0, snow_in_hr=0.0)
STRAIGHT = [(40.0, -100.0), (40.0, -98.0)]


def route(miles_by_severity=None, unknown=0.0, total=100.0, duration=3600.0, route_id="A"):
    miles = dict.fromkeys(Severity, 0.0)
    miles.update(miles_by_severity or {})
    known = sum(miles.values())
    average = sum(m * s.value for s, m in miles.items()) / known if known else None
    summary = SeveritySummary(
        miles=miles, unknown_miles=unknown, total_miles=total, weighted_average_risk=average
    )
    return RouteScore(route_id=route_id, duration_seconds=duration, summary=summary)


# --- mileage accounting ------------------------------------------------------------------------------


def test_mileage_uses_intervals_not_checkpoint_counts():
    # 57.3 mi at 25 mi spacing: checkpoints at 0, 25, 50, 57.3. Only the 50-mile checkpoint is severe.
    def lookup(lat, lon, eta):
        severe_eta = DEPARTURE + timedelta(seconds=3600 * 50 / 57.3)
        return WeatherSample(60.0 if abs((eta - severe_eta).total_seconds()) < 1 else 5.0, 0.0, 0.0)

    checkpoints = build_checkpoints(
        STRAIGHT, 57.3, 25, DEPARTURE, TimingCurve.proportional(57.3, 3600), lookup, load_lb=10_000
    )
    summary = summarize(checkpoints, 57.3)
    assert summary.miles[NT] == pytest.approx(53.65 - 37.5)
    assert summary.miles[L] == pytest.approx(57.3 - (53.65 - 37.5))
    assert sum(summary.miles.values()) + summary.unknown_miles == pytest.approx(57.3, abs=1e-6)


def test_weighted_average_is_distance_weighted_over_known_miles():
    def lookup(lat, lon, eta):
        return WeatherSample(40.0, 0.0, 0.0) if eta == DEPARTURE else WeatherSample(None, 0.0, 0.0)

    checkpoints = build_checkpoints(
        STRAIGHT, 30.0, 10, DEPARTURE, TimingCurve.proportional(30.0, 3600), lookup, load_lb=10_000
    )
    summary = summarize(checkpoints, 30.0)
    assert summary.miles[H] == pytest.approx(5.0)  # origin owns [0, 5]
    assert summary.unknown_miles == pytest.approx(25.0)
    assert summary.weighted_average_risk == pytest.approx(2.0)
    assert not summary.is_verified


def test_checkpoints_query_weather_at_each_eta_not_departure():
    seen = []

    def lookup(lat, lon, eta):
        seen.append(eta)
        return CALM

    build_checkpoints(STRAIGHT, 100.0, 50, DEPARTURE, TimingCurve.proportional(100.0, 7200), lookup, 10_000)
    assert seen == [DEPARTURE, DEPARTURE + timedelta(hours=1), DEPARTURE + timedelta(hours=2)]


def test_all_unknown_route_has_no_average():
    summary = summarize([], 10.0)
    assert summary.weighted_average_risk is None


# --- ranking -----------------------------------------------------------------------------------------


def test_slower_route_with_fewer_severe_miles_wins():
    fast = route({S: 10, L: 90}, duration=3600, route_id="fast")
    slow = route({S: 2, H: 50, L: 48}, duration=7200, route_id="slow")
    result = recommend([fast, slow])
    assert result.status == RecommendationStatus.RECOMMENDED
    assert result.recommended_route_id == "slow"
    assert "fewest Severe miles" in result.reason


def test_high_miles_break_severe_tie():
    a = route({S: 5, H: 20, L: 75}, route_id="A")
    b = route({S: 5, H: 10, M: 85}, route_id="B")
    result = recommend([a, b])
    assert result.recommended_route_id == "B"
    assert "fewest High miles" in result.reason


def test_average_risk_breaks_severe_and_high_tie():
    a = route({H: 10, M: 60, L: 30}, duration=100, route_id="A")
    b = route({H: 10, M: 20, L: 70}, duration=900, route_id="B")
    result = recommend([a, b])
    assert result.recommended_route_id == "B"
    assert "lowest average risk" in result.reason


def test_duration_breaks_full_weather_tie():
    a = route({L: 100}, duration=5000, route_id="A")
    b = route({L: 100}, duration=4000, route_id="B")
    result = recommend([a, b])
    assert result.recommended_route_id == "B"
    assert "shortest travel time" in result.reason


def test_route_id_is_deterministic_final_tiebreak():
    result = recommend([route({L: 100}, route_id="B"), route({L: 100}, route_id="A")])
    assert result.recommended_route_id == "A"
    assert "route ID" in result.reason


def test_float_noise_does_not_flip_tie():
    a = route({S: 0.1 + 0.2, L: 99.7}, duration=100, route_id="A")
    b = route({S: 0.3, L: 99.7}, duration=200, route_id="B")
    assert recommend([a, b]).recommended_route_id == "A"


def test_no_travel_route_excluded_even_if_otherwise_best():
    risky = route({NT: 0.5, L: 99.5}, duration=1000, route_id="risky")
    severe = route({S: 40, L: 60}, duration=9000, route_id="severe")
    result = recommend([risky, severe])
    assert result.recommended_route_id == "severe"
    standings = {r.route_id: r.standing for r in result.ranked}
    assert standings == {"severe": RouteStanding.RECOMMENDED, "risky": RouteStanding.NO_TRAVEL}
    assert "No Travel" in next(r.note for r in result.ranked if r.route_id == "risky")


def test_all_no_travel_routes_give_no_safe_route():
    result = recommend([route({NT: 5, L: 95}, route_id="A"), route({NT: 1, S: 99}, route_id="B")])
    assert result.status == RecommendationStatus.NO_SAFE_ROUTE
    assert result.recommended_route_id is None
    assert all(r.standing == RouteStanding.NO_TRAVEL for r in result.ranked)
    assert [r.route_id for r in result.ranked] == ["B", "A"]  # least No Travel exposure first


def test_unverified_route_is_never_recommended():
    unverified = route({L: 50}, unknown=50, duration=100, route_id="A")
    verified = route({S: 30, L: 70}, duration=9000, route_id="B")
    result = recommend([unverified, verified])
    assert result.recommended_route_id == "B"
    assert result.ranked[1].standing == RouteStanding.UNVERIFIED


def test_only_unverified_and_no_travel_routes_give_insufficient_data():
    result = recommend([route({L: 50}, unknown=50, route_id="A"), route({NT: 10, L: 90}, route_id="B")])
    assert result.status == RecommendationStatus.INSUFFICIENT_DATA
    assert result.recommended_route_id is None


def test_single_eligible_route_explains_why():
    result = recommend([route({L: 100}, route_id="A"), route({NT: 1, L: 99}, route_id="B")])
    assert result.recommended_route_id == "A"
    assert "only route" in result.reason


def test_recommend_rejects_empty_and_duplicate_ids():
    with pytest.raises(ValueError):
        recommend([])
    with pytest.raises(ValueError):
        recommend([route(route_id="A"), route(route_id="A")])
