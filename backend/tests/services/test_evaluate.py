from datetime import UTC, datetime, timedelta

import pytest

from routing.providers.errors import ProviderUnavailable
from routing.services.evaluate import (
    Place,
    Providers,
    Settings,
    TripRequest,
    TripValidationError,
    evaluate_trip,
)
from tests.fakes import (
    CHICAGO,
    ROCKFORD,
    FakeForecaster,
    FakeGeocoder,
    FakeRouter,
    straight_route,
    three_routes,
)

DEPARTURE = datetime(2026, 10, 20, 13, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
SETTINGS = Settings(empty_truck_lb=35_000, alternatives=2)


def trip(load=20_000, spacing=10, departure=DEPARTURE, origin="Chicago, IL", destination="Rockford, IL"):
    return TripRequest(
        origin=Place(query=origin, coordinates=None),
        destination=Place(query=destination, coordinates=None),
        departure=departure,
        timezone="America/Chicago",
        load_lb=load,
        spacing_miles=spacing,
    )


def run(router=None, forecaster=None, geocoder=None, request=None):
    providers = Providers(geocoder or FakeGeocoder(), router or FakeRouter(), forecaster or FakeForecaster())
    return evaluate_trip(request or trip(), providers, SETTINGS, now=NOW)


def by_id(result):
    return {route["id"]: route for route in result["routes"]}


def south_of(lat_limit, wind):
    """Wind ``wind`` mph south of ``lat_limit`` (route B dips south through Joliet), calm elsewhere."""
    return lambda lat, lon, at: (wind if lat < lat_limit else 5.0, 0.0, 0.0)


def test_calm_trip_recommends_fastest_route_with_full_payload():
    router = FakeRouter()
    result = run(router=router)
    assert result["recommendation"]["status"] == "recommended"
    assert result["recommendation"]["route_id"] == "A"
    assert "shortest travel time" in result["recommendation"]["reason"]
    assert [r["id"] for r in result["routes"]] == ["A", "C", "B"]  # ordered by rank
    assert router.calls[0]["weight_kg"] == 24_948  # (35,000 + 20,000 lb) in kg
    assert router.calls[0]["alternatives"] == 2
    assert result["request"]["routing_weight_lb"] == 55_000
    route_a = by_id(result)["A"]
    assert route_a["is_recommended"] and route_a["eligible"] and route_a["verified"]
    assert route_a["geometry"]["coordinates"][0] == [CHICAGO[1], CHICAGO[0]]  # GeoJSON [lon, lat]
    assert route_a["severity_miles"]["low"] == pytest.approx(90.0)
    # Fake route C has no span timing, so only its approximated ETA is disclosed.
    assert [(w["code"], w["route_id"]) for w in result["warnings"]] == [("eta_approximated", "C")]


def test_checkpoints_use_eta_at_each_distance_from_provider_spans():
    route_b = by_id(run())["B"]
    checkpoints = route_b["checkpoints"]
    assert checkpoints[0]["distance_miles"] == 0 and checkpoints[-1]["distance_miles"] == 120.0
    assert len(checkpoints) == 13  # 0, 10, ..., 120
    eta = {c["distance_miles"]: c["eta"] for c in checkpoints}
    assert eta[0.0] == "2026-10-20T13:00:00Z"
    assert eta[60.0] == "2026-10-20T13:50:00Z"  # first span: 60 mi in 3000 s
    assert eta[120.0] == "2026-10-20T15:00:00Z"  # second span is slower: 60 mi in 4200 s
    assert route_b["eta_method"] == "provider_segments"
    assert route_b["arrival_at"] == "2026-10-20T15:00:00Z"
    total = sum(c["interval_end_miles"] - c["interval_start_miles"] for c in checkpoints)
    assert total == pytest.approx(120.0, abs=1e-6)


def test_weather_is_fetched_once_for_all_routes_at_checkpoint_positions():
    forecaster = FakeForecaster()
    result = run(forecaster=forecaster)
    assert len(forecaster.calls) == 1
    locations, hours = forecaster.calls[0]
    checkpoint_count = sum(len(r["checkpoints"]) for r in result["routes"])
    assert len(locations) <= checkpoint_count  # shared origin/destination deduplicated
    assert hours == 4  # latest ETA 15:00Z is 3 h after "now" (12:00Z), +1


def test_severe_wind_on_faster_route_makes_slower_route_win():
    # Route A and C stay north; B dips south. Put severe wind on the north instead.
    weather = lambda lat, lon, at: (50.0 if lat > 41.95 else 5.0, 0.0, 0.0)  # noqa: E731
    result = run(forecaster=FakeForecaster(weather))
    routes = by_id(result)
    assert routes["A"]["severity_miles"]["severe"] > routes["B"]["severity_miles"]["severe"]
    assert result["recommendation"]["route_id"] == "B"
    assert "fewest Severe miles" in result["recommendation"]["reason"]


def test_load_rule_turns_45_mph_wind_into_no_travel_above_30000_lb():
    weather = south_of(41.7, 47.0)
    at_limit = by_id(run(forecaster=FakeForecaster(weather), request=trip(load=30_000)))["B"]
    over = run(forecaster=FakeForecaster(weather), request=trip(load=30_001))
    assert at_limit["severity_miles"]["no_travel"] == 0 and at_limit["severity_miles"]["severe"] > 0
    route_b = by_id(over)["B"]
    assert route_b["severity_miles"]["no_travel"] > 0
    assert route_b["standing"] == "no_travel" and not route_b["eligible"]
    assert any(c["factors"] == ["wind", "load"] for c in route_b["checkpoints"])
    assert [w["route_id"] for w in over["warnings"] if w["code"] == "no_travel"] == ["B"]


def test_all_routes_no_travel_gives_no_safe_route_and_nothing_recommended():
    result = run(forecaster=FakeForecaster(lambda lat, lon, at: (60.0, 0.0, 0.0)))
    assert result["recommendation"]["status"] == "no_safe_route"
    assert result["recommendation"]["route_id"] is None
    assert not any(r["is_recommended"] for r in result["routes"])
    assert {w["route_id"] for w in result["warnings"] if w["code"] == "no_travel"} == {"A", "B", "C"}


def test_weather_provider_failure_keeps_routes_but_everything_is_unknown():
    forecaster = FakeForecaster(error=ProviderUnavailable("Open-Meteo", "HTTP 503"))
    result = run(forecaster=forecaster)
    assert result["recommendation"]["status"] == "insufficient_data"
    assert result["recommendation"]["route_id"] is None
    assert all(c["severity"] == "unknown" for r in result["routes"] for c in r["checkpoints"])
    assert all(r["severity_miles"]["unknown"] == r["distance_miles"] for r in result["routes"])
    assert all(r["weighted_average_risk"] is None for r in result["routes"])
    codes = [w["code"] for w in result["warnings"]]
    assert "weather_unavailable" in codes and "partial_forecast" not in codes


def test_eta_beyond_forecast_coverage_is_unknown_and_route_not_recommended():
    # Series ends at 14:00Z: later checkpoints of every route have no forecast.
    forecaster = FakeForecaster(start=datetime(2026, 10, 20, 10, tzinfo=UTC), hours=5)
    result = run(forecaster=forecaster)
    assert result["recommendation"]["status"] == "insufficient_data"
    for route in result["routes"]:
        assert route["severity_miles"]["unknown"] > 0
        assert route["standing"] == "unverified"
    assert {w["route_id"] for w in result["warnings"] if w["code"] == "partial_forecast"} == {"A", "B", "C"}


def test_missing_value_never_counts_as_low():
    result = run(forecaster=FakeForecaster(lambda lat, lon, at: (5.0, None, 0.0)))
    assert all(r["severity_miles"]["low"] == 0 for r in result["routes"])
    assert result["recommendation"]["status"] == "insufficient_data"


def test_fewer_routes_than_requested_are_returned_without_padding():
    result = run(router=FakeRouter(routes=three_routes()[:1]))
    assert [r["id"] for r in result["routes"]] == ["A"]
    assert result["provider"]["routes_returned"] == 1
    warning = next(w for w in result["warnings"] if w["code"] == "fewer_routes_than_requested")
    assert "1 distinct truck route(s) of 3" in warning["message"]
    assert result["recommendation"]["route_id"] == "A"
    assert "only route" in result["recommendation"]["reason"]


def test_duplicate_alternatives_are_removed_and_reported():
    first = three_routes()[0]
    duplicate = straight_route("B", (42.05, -88.30), 90.0, 5400)
    result = run(router=FakeRouter(routes=[first, duplicate]))
    assert [r["id"] for r in result["routes"]] == ["A"]
    assert result["provider"]["duplicates_removed"] == 1


def test_proportional_eta_and_provider_notices_are_disclosed():
    route = straight_route(
        "A", (42.05, -88.30), 90.0, 5400, notices=["Road forbidden for the vehicle profile."]
    )
    result = run(router=FakeRouter(routes=[route]))
    assert result["routes"][0]["eta_method"] == "proportional"
    codes = {w["code"] for w in result["warnings"]}
    assert {"eta_approximated", "provider_notice"} <= codes


def test_heavy_truck_warning_when_gross_exceeds_legal_limit():
    result = run(request=trip(load=50_000))
    assert any(w["code"] == "gross_weight_over_legal_limit" for w in result["warnings"])


def test_coordinates_skip_geocoding_and_same_place_is_rejected():
    geocoder = FakeGeocoder()
    request = TripRequest(
        origin=Place(None, CHICAGO),
        destination=Place(None, ROCKFORD),
        departure=DEPARTURE,
        timezone="UTC",
        load_lb=10_000,
        spacing_miles=25,
    )
    result = run(geocoder=geocoder, request=request)
    assert geocoder.queries == []
    assert result["request"]["origin"]["lat"] == CHICAGO[0]
    same = TripRequest(Place(None, CHICAGO), Place(None, CHICAGO), DEPARTURE, "UTC", 10_000, 25)
    with pytest.raises(TripValidationError):
        run(geocoder=geocoder, request=same)


def test_heatmap_reference_is_departure_hour_and_corridor_is_bounded():
    result = run(request=trip(departure=DEPARTURE + timedelta(minutes=40)))
    assert result["heatmap_reference_at"] == "2026-10-20T13:00:00Z"
    assert 0 < len(result["corridor"]) <= 2000


class ProviderWindowForecaster(FakeForecaster):
    """Like Open-Meteo: returns exactly `forecast_hours` hours starting at the current hour."""

    def __init__(self, now):
        super().__init__()
        self.now = now

    def hourly_forecasts(self, locations, forecast_hours):
        self.start = self.now.replace(minute=0, second=0, microsecond=0)
        self.hours = forecast_hours
        return super().hourly_forecasts(locations, forecast_hours)


def test_forecast_window_covers_latest_eta_when_now_is_mid_hour():
    # now 12:40, route A arrives 14:30: the window must include 15:00 for the destination checkpoint.
    now = datetime(2026, 10, 20, 12, 40, tzinfo=UTC)
    providers = Providers(
        FakeGeocoder(), FakeRouter(routes=three_routes()[:1]), ProviderWindowForecaster(now)
    )
    result = evaluate_trip(trip(), providers, SETTINGS, now=now)
    route = result["routes"][0]
    assert route["checkpoints"][-1]["eta"] == "2026-10-20T14:30:00Z"
    assert route["checkpoints"][-1]["severity"] != "unknown"
    assert route["verified"] is True


def test_corridor_is_capped_without_dropping_any_route_destination():
    # Three very long routes: naive sampling would exceed the cap and truncate the last route.
    routes = [
        straight_route(rid, via, 6000.0, 6000 * 60)
        for rid, via in (("A", (42.05, -88.3)), ("B", (41.5, -88.1)), ("C", (42.4, -88.0)))
    ]
    result = run(router=FakeRouter(routes=routes), request=trip(spacing=50))
    corridor = result["corridor"]
    assert len(corridor) <= 2000
    destination = [round(ROCKFORD[1], 5), round(ROCKFORD[0], 5)]
    assert corridor.count(destination) == 3  # every route still ends at the destination


def test_ambiguous_departure_warning_comes_from_the_service():
    request = TripRequest(
        Place("Chicago, IL", None),
        Place("Rockford, IL", None),
        DEPARTURE,
        "America/Chicago",
        20_000,
        10,
        departure_ambiguous=True,
    )
    result = run(request=request)
    assert [w["code"] for w in result["warnings"]].count("ambiguous_local_time") == 1
