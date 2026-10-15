from datetime import datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
import responses

from routing.domain.units import gross_weight_kg, meters_to_miles
from routing.providers.errors import NoRouteFound, PlaceNotFound, ProviderConfigError
from routing.providers.here import HereGeocoder, HereTruckRouter
from tests.providers.conftest import load_fixture

ROUTES_URL = "https://router.test/v8/routes"
GEOCODE_URL = "https://geocode.test/v1/geocode"
DEPARTURE = datetime(2026, 10, 20, 8, 0, tzinfo=ZoneInfo("America/Chicago"))


def router(client_factory, key="k"):
    return HereTruckRouter(client_factory("HERE"), "https://router.test/v8/", key)


WEIGHT_KG = gross_weight_kg(40_000, 35_000)


def call_routes(client_factory, weight_kg=WEIGHT_KG):
    return router(client_factory).truck_routes((41.88, -87.63), (41.4, -89.5), DEPARTURE, weight_kg, 2)


def query(call):
    return {k: v[0] for k, v in parse_qs(urlparse(call.request.url).query).items()}


@responses.activate
def test_truck_request_parameters(client_factory):
    responses.get(ROUTES_URL, json=load_fixture("here_routes_synthetic.json"))
    call_routes(client_factory)
    params = query(responses.calls[0])
    assert params["transportMode"] == "truck"
    assert params["alternatives"] == "2"
    assert params["departureTime"] == "2026-10-20T13:00:00Z"
    assert params["return"] == "polyline,summary"
    assert params["spans"] == "duration,length"
    # 35,000 lb empty + 40,000 lb cargo = 75,000 lb = 34,019 kg (HERE expects integer kg).
    assert params["vehicle[grossWeight]"] == "34019"
    assert params["vehicle[currentWeight]"] == "34019"
    assert not any(key.startswith("truck[") for key in params)


@responses.activate
def test_parses_routes_geometry_distance_and_duration(client_factory):
    responses.get(ROUTES_URL, json=load_fixture("here_routes_synthetic.json"))
    route_a, route_b = call_routes(client_factory)
    assert (route_a.route_id, route_b.route_id) == ("A", "B")
    assert route_a.distance_miles == pytest.approx(meters_to_miles(150_000))
    assert route_a.duration_seconds == 6600
    # Sections share the joint point (41.6, -88.5): 4 + 3 points -> 6.
    assert len(route_a.points) == 6
    assert route_a.points[0] == (41.88, -87.63)
    assert route_a.points[-1] == (41.4, -89.5)


@responses.activate
def test_span_timing_includes_section_waiting_time(client_factory):
    responses.get(ROUTES_URL, json=load_fixture("here_routes_synthetic.json"))
    route_a, _ = call_routes(client_factory)
    assert route_a.timing_segments is not None
    lengths = [length for length, _ in route_a.timing_segments]
    durations = [duration for _, duration in route_a.timing_segments]
    assert durations == [1200, 1200, 1200, 600, 1500, 900]  # 600 s stop before section 2
    assert lengths[3] == 0.0
    assert sum(durations) == route_a.duration_seconds
    assert sum(lengths) == pytest.approx(route_a.distance_miles)


@responses.activate
def test_route_without_spans_falls_back_and_reports_critical_notices(client_factory):
    responses.get(ROUTES_URL, json=load_fixture("here_routes_synthetic.json"))
    route_a, route_b = call_routes(client_factory)
    assert route_b.timing_segments is None
    assert route_b.notices == ["Route uses a road which is forbidden for the given vehicle profile."]
    assert route_a.notices == []  # info-level notices are not warnings


@responses.activate
def test_fewer_alternatives_are_returned_as_is(client_factory):
    body = load_fixture("here_routes_synthetic.json")
    body["routes"] = body["routes"][:1]
    responses.get(ROUTES_URL, json=body)
    assert [r.route_id for r in call_routes(client_factory)] == ["A"]


@responses.activate
def test_no_route_found_uses_provider_notice(client_factory):
    responses.get(
        ROUTES_URL, json={"routes": [], "notices": [{"title": "No route found", "code": "noRouteFound"}]}
    )
    with pytest.raises(NoRouteFound, match="No route found"):
        call_routes(client_factory)


def test_missing_api_key_fails_before_any_request(client_factory):
    with responses.RequestsMock() as mocked, pytest.raises(ProviderConfigError, match="HERE_API_KEY"):
        router(client_factory, key="").truck_routes((0, 0), (1, 1), DEPARTURE, 1, 2)
    assert len(mocked.calls) == 0


@responses.activate
def test_geocode_parses_first_item_and_restricts_country(client_factory):
    responses.get(
        GEOCODE_URL,
        json={
            "items": [
                {
                    "title": "Chicago, IL, United States",
                    "resultType": "locality",
                    "address": {"label": "Chicago, IL, United States", "countryCode": "USA"},
                    "position": {"lat": 41.88425, "lng": -87.63245},
                }
            ]
        },
    )
    place = HereGeocoder(client_factory("HERE"), "https://geocode.test/v1", "k", "USA").geocode("Chicago")
    assert (place.label, place.lat, place.lon) == ("Chicago, IL, United States", 41.88425, -87.63245)
    params = query(responses.calls[0])
    assert params["in"] == "countryCode:USA"
    assert params["limit"] == "1"


@responses.activate
def test_geocode_no_match(client_factory):
    responses.get(GEOCODE_URL, json={"items": []})
    with pytest.raises(PlaceNotFound):
        HereGeocoder(client_factory("HERE"), "https://geocode.test/v1", "k", "").geocode("nowhere")


@responses.activate
def test_span_without_offset_falls_back_to_proportional_eta(client_factory):
    body = load_fixture("here_routes_synthetic.json")
    del body["routes"][0]["sections"][0]["spans"][1]["offset"]
    responses.get(ROUTES_URL, json=body)
    route_a, _ = call_routes(client_factory)
    assert route_a.timing_segments is None  # disclosed proportional fallback, not a 502


@responses.activate
def test_span_time_longer_than_summary_is_scaled_to_summary(client_factory):
    body = load_fixture("here_routes_synthetic.json")
    for span in body["routes"][0]["sections"][0]["spans"]:
        span["duration"] = 1500  # 4,500 s of spans vs a 3,600 s summary
    responses.get(ROUTES_URL, json=body)
    route_a, _ = call_routes(client_factory)
    assert route_a.timing_segments is not None
    assert sum(seconds for _, seconds in route_a.timing_segments) == pytest.approx(route_a.duration_seconds)


def test_route_and_geocode_caches_serve_repeats():
    from django.core.cache import caches

    from routing.providers.base import GeocodedPlace
    from routing.providers.cache import CachedGeocoder, CachedRouter

    cache = caches["default"]
    cache.clear()

    class CountingGeocoder:
        calls = 0

        def geocode(self, query):
            CountingGeocoder.calls += 1
            return GeocodedPlace(query, 41.0, -87.0)

    class CountingRouter:
        description = "counting"
        calls = 0

        def truck_routes(self, origin, destination, departure, weight_kg, alternatives):
            CountingRouter.calls += 1
            return []

    geocoder = CachedGeocoder(CountingGeocoder(), cache)
    geocoder.geocode("Chicago, IL")
    geocoder.geocode("  chicago,   il ")  # same place after normalising case and spaces
    assert CountingGeocoder.calls == 1

    router = CachedRouter(CountingRouter(), cache, timeout_s=60)
    router.truck_routes((41.0, -87.0), (39.7, -105.0), DEPARTURE, 34_019, 2)
    router.truck_routes((41.0, -87.0), (39.7, -105.0), DEPARTURE, 34_019, 2)
    router.truck_routes((41.0, -87.0), (39.7, -105.0), DEPARTURE, 40_000, 2)  # different weight
    assert CountingRouter.calls == 2
    assert router.description == "counting"
    cache.clear()
