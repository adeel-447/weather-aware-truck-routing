import gzip
import json
from datetime import UTC, datetime

import pytest
from django.test import Client

from routing import serializers as request_serializers
from routing.providers import factory
from routing.providers.errors import (
    NoRouteFound,
    ProviderConfigError,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from tests.fakes import FakeForecaster, FakeGeocoder, FakeRouter

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
EVALUATE = "/api/routes/evaluate/"
HEATMAP = "/api/heatmap/"
VALID = {
    "origin": "Chicago, IL",
    "destination": "Rockford, IL",
    "departure_at": "2026-10-20T08:00:00-05:00",
    "timezone": "America/Chicago",
    "load_weight_lb": 38_000,
    "checkpoint_spacing_miles": 25,
}


@pytest.fixture
def providers(monkeypatch):
    fakes = {"geocoder": FakeGeocoder(), "router": FakeRouter(), "forecaster": FakeForecaster()}
    monkeypatch.setattr(factory, "get_geocoder", lambda: fakes["geocoder"])
    monkeypatch.setattr(factory, "get_router", lambda: fakes["router"])
    monkeypatch.setattr(factory, "get_forecaster", lambda: fakes["forecaster"])
    monkeypatch.setattr(request_serializers, "_now", lambda: NOW)
    return fakes


def post(path, body):
    return Client().post(path, data=json.dumps(body), content_type="application/json")


def error_of(response):
    body = response.json()
    assert set(body) == {"error"}
    return body["error"]


# --- evaluate: success -------------------------------------------------------------------------------


def test_evaluate_success_shape(providers):
    response = post(EVALUATE, VALID)
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {
        "request",
        "recommendation",
        "routes",
        "warnings",
        "corridor",
        "heatmap_reference_at",
        "provider",
        "assumptions",
    }
    assert body["request"]["departure_at"] == "2026-10-20T13:00:00Z"
    assert body["recommendation"]["status"] == "recommended"
    route = body["routes"][0]
    assert route["geometry"]["type"] == "LineString"
    assert set(route["severity_miles"]) == {"low", "moderate", "high", "severe", "no_travel", "unknown"}
    checkpoint = route["checkpoints"][0]
    assert set(checkpoint) >= {"eta", "weather", "severity", "severity_score", "factors", "distance_miles"}


def test_naive_departure_is_local_time_in_given_timezone(providers):
    response = post(EVALUATE, {**VALID, "departure_at": "2026-10-20T08:00"})
    assert response.status_code == 200
    assert response.json()["request"]["departure_at"] == "2026-10-20T13:00:00Z"  # CDT = UTC-5


def test_ambiguous_dst_local_time_uses_first_occurrence_and_warns(providers, monkeypatch):
    monkeypatch.setattr(request_serializers, "_now", lambda: datetime(2026, 10, 31, 12, tzinfo=UTC))
    response = post(EVALUATE, {**VALID, "departure_at": "2026-11-01T01:30"})
    assert response.status_code == 200
    body = response.json()
    assert body["request"]["departure_at"] == "2026-11-01T06:30:00Z"  # first 01:30 is CDT
    assert any(w["code"] == "ambiguous_local_time" for w in body["warnings"])


def test_coordinates_are_accepted_without_geocoding(providers):
    response = post(EVALUATE, {**VALID, "origin": "41.88,-87.63", "destination": "42.27, -89.09"})
    assert response.status_code == 200
    assert providers["geocoder"].queries == []


def test_unsafe_trip_is_never_presented_as_safe(providers):
    providers["forecaster"] = FakeForecaster(lambda lat, lon, at: (60.0, 0.0, 0.0))
    body = post(EVALUATE, VALID).json()
    assert body["recommendation"] == {
        "status": "no_safe_route",
        "route_id": None,
        "reason": "No safe route: every route has No Travel conditions at the estimated arrival times.",
    }
    assert not any(route["is_recommended"] for route in body["routes"])


def test_single_route_from_provider(providers):
    providers["router"].routes = providers["router"].routes[:1]
    body = post(EVALUATE, VALID).json()
    assert len(body["routes"]) == 1
    assert "fewer_routes_than_requested" in [w["code"] for w in body["warnings"]]


# --- evaluate: validation ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"checkpoint_spacing_miles": 30}, "checkpoint_spacing_miles"),
        ({"load_weight_lb": 0}, "load_weight_lb"),
        ({"load_weight_lb": 80_001}, "load_weight_lb"),
        ({"load_weight_lb": "heavy"}, "load_weight_lb"),
        ({"timezone": "Mars/Base"}, "timezone"),
        ({"departure_at": "tomorrow"}, "departure_at"),
        ({"departure_at": "2026-10-20T08:00:00Z".replace("10-20", "10-19")}, "departure_at"),  # past
        ({"departure_at": "2026-10-27T08:00:00Z"}, "departure_at"),  # beyond 6 days
        ({"destination": "Chicago, IL"}, "destination"),
        ({"origin": "95.0,10.0"}, "origin"),
        ({"origin": ""}, "origin"),
    ],
)
def test_invalid_inputs_return_400_with_field_errors(providers, change, field):
    response = post(EVALUATE, {**VALID, **change})
    assert response.status_code == 400
    error = error_of(response)
    assert error["code"] == "invalid_request"
    assert field in error["fields"]
    assert providers["router"].calls == []


def test_missing_fields_are_listed(providers):
    error = error_of(post(EVALUATE, {}))
    assert set(error["fields"]) == {
        "origin",
        "destination",
        "departure_at",
        "load_weight_lb",
        "checkpoint_spacing_miles",
    }


def test_nonexistent_local_time_in_spring_forward_gap(providers, monkeypatch):
    monkeypatch.setattr(request_serializers, "_now", lambda: datetime(2027, 3, 13, 12, tzinfo=UTC))
    error = error_of(post(EVALUATE, {**VALID, "departure_at": "2027-03-14T02:30"}))
    assert "does not exist" in str(error["fields"]["departure_at"])


def test_malformed_json_and_wrong_method(providers):
    bad = Client().post(EVALUATE, data="{not json", content_type="application/json")
    assert bad.status_code == 400
    assert error_of(bad)["code"] == "parse_error"
    wrong = Client().get(EVALUATE)
    assert wrong.status_code == 405
    assert error_of(wrong)["code"] == "method_not_allowed"


def test_same_place_after_geocoding_is_rejected(providers):
    places = providers["geocoder"].places
    places["Downtown Chicago"] = places["Chicago, IL"]
    error = error_of(post(EVALUATE, {**VALID, "destination": "Downtown Chicago"}))
    assert error["code"] == "invalid_request"
    assert "same place" in error["message"]
    assert set(error["fields"]) == {"origin", "destination"}  # either input may be wrong


# --- evaluate: provider failures ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (ProviderUnavailable("HERE", "HTTP 503"), 503, "provider_unavailable"),
        (ProviderTimeout("HERE", "request timed out"), 504, "provider_timeout"),
        (NoRouteFound("HERE", "No route found"), 422, "no_route_found"),
        (ProviderConfigError("HERE", "HERE_API_KEY is not configured"), 503, "provider_not_configured"),
    ],
)
def test_routing_failures_map_to_clear_errors(providers, exc, status, code):
    providers["router"].error = exc
    response = post(EVALUATE, VALID)
    assert response.status_code == status
    error = error_of(response)
    assert (error["code"], error["provider"]) == (code, "HERE")
    assert error["message"] == exc.message


@pytest.mark.parametrize("field", ["origin", "destination"])
def test_geocoding_miss_is_422_and_names_the_field(providers, field, caplog):
    response = post(EVALUATE, {**VALID, field: "Atlantis"})
    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "place_not_found"
    assert error["provider"] == "HERE"
    assert error["fields"] == {field: ["no location found for 'Atlantis'"]}
    assert "provider failure" in caplog.text  # misses stay visible in the logs


def test_weather_outage_still_returns_routes_marked_unknown(providers):
    providers["forecaster"].error = ProviderUnavailable("Open-Meteo", "HTTP 503")
    response = post(EVALUATE, VALID)
    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"]["status"] == "insufficient_data"
    assert "weather_unavailable" in [w["code"] for w in body["warnings"]]


def test_unexpected_error_uses_envelope(providers, monkeypatch):
    providers["router"].error = RuntimeError("boom")
    response = post(EVALUATE, VALID)
    assert response.status_code == 500
    assert error_of(response) == {"code": "internal_error", "message": "Unexpected server error."}


# --- heatmap -----------------------------------------------------------------------------------------

HEATMAP_BODY = {
    "corridor": [[-87.63, 41.88], [-88.3, 42.05], [-89.09, 42.27]],
    "reference_at": "2026-10-20T13:00:00Z",
    "load_weight_lb": 38_000,
}


def test_heatmap_success_is_bounded_and_complete(providers):
    response = post(HEATMAP, HEATMAP_BODY)
    assert response.status_code == 200
    body = response.json()
    assert len(body["frames"]) == 49
    assert 0 < len(body["cells"]) <= 200  # HEATMAP_MAX_CELLS default
    assert body["layer"] == "composite_severity"
    assert body["units"] == {"wind_mph": "mph", "rain_in_hr": "in/hr", "snow_in_hr": "in/hr"}
    assert len(providers["forecaster"].calls) == 1


def test_heatmap_response_is_gzip_compressed(providers):
    response = Client().post(
        HEATMAP, data=json.dumps(HEATMAP_BODY), content_type="application/json", HTTP_ACCEPT_ENCODING="gzip"
    )
    assert response["Content-Encoding"] == "gzip"
    assert len(json.loads(gzip.decompress(response.content))["frames"]) == 49


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"corridor": []}, "corridor"),
        ({"corridor": [[-87.63]]}, "corridor"),
        ({"corridor": [[200.0, 41.0]]}, "corridor"),
        ({"corridor": [[-87.0, 41.0]] * 2001}, "corridor"),
        ({"reference_at": "2026-12-01T00:00:00Z"}, "reference_at"),
        ({"load_weight_lb": -5}, "load_weight_lb"),
    ],
)
def test_heatmap_validation(providers, change, field):
    response = post(HEATMAP, {**HEATMAP_BODY, **change})
    assert response.status_code == 400
    assert field in error_of(response)["fields"]
    assert providers["forecaster"].calls == []


def test_heatmap_weather_outage_is_explicit(providers):
    providers["forecaster"].error = ProviderUnavailable("Open-Meteo", "HTTP 503")
    response = post(HEATMAP, HEATMAP_BODY)
    assert response.status_code == 503
    assert error_of(response)["provider"] == "Open-Meteo"


def test_heatmap_rate_limit_is_explicit(providers):
    providers["forecaster"].error = ProviderRateLimited("Open-Meteo", "Minutely API request limit exceeded.")
    response = post(HEATMAP, HEATMAP_BODY)
    assert response.status_code == 503
    assert error_of(response)["code"] == "provider_rate_limited"


def test_heatmap_grid_respects_configured_cap(providers, settings):
    settings.HEATMAP_MAX_CELLS = 20
    long_corridor = [[-87.63 - i * 0.04, 41.88 - i * 0.005] for i in range(400)]
    body = post(HEATMAP, {**HEATMAP_BODY, "corridor": long_corridor}).json()
    assert len(body["cells"]) <= 20
    assert body["cell_size_degrees"] > 0.1


def test_heatmap_does_not_touch_routing(providers):
    post(HEATMAP, HEATMAP_BODY)
    assert providers["router"].calls == []


def test_heatmap_reference_error_message_matches_rule(providers):
    error = error_of(post(HEATMAP, {**HEATMAP_BODY, "reference_at": "2026-10-18T06:00:00Z"}))  # 54 h ago
    assert "between 48 hours ago and 6 days ahead" in str(error["fields"]["reference_at"])


def test_heatmap_retry_for_an_evaluation_left_on_screen_is_accepted(providers):
    # Reference 30 h before "now": the evaluation is old but still on screen; past frames are unavailable.
    response = post(HEATMAP, {**HEATMAP_BODY, "reference_at": "2026-10-19T06:00:00Z"})
    assert response.status_code == 200


def test_departure_before_the_current_hour_is_rejected(providers, monkeypatch):
    monkeypatch.setattr(request_serializers, "_now", lambda: datetime(2026, 10, 20, 13, 5, tzinfo=UTC))
    early = post(EVALUATE, {**VALID, "departure_at": "2026-10-20T12:55:00Z"})
    assert early.status_code == 400
    assert "current hour or later" in str(error_of(early)["fields"]["departure_at"])
    # The start of the current hour is the first forecast hour, so it is accepted.
    assert post(EVALUATE, {**VALID, "departure_at": "2026-10-20T13:00:00Z"}).status_code == 200


def test_response_names_the_routing_source(providers):
    assert post(EVALUATE, VALID).json()["provider"]["routing"] == "Fake truck router"


def test_requests_are_throttled_per_client_with_retry_after(providers, monkeypatch):
    from django.core.cache import cache
    from rest_framework.throttling import ScopedRateThrottle

    cache.clear()
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"evaluate": "1/min", "heatmap": "1/min"})
    assert post(EVALUATE, VALID).status_code == 200
    throttled = post(EVALUATE, VALID)
    assert throttled.status_code == 429
    assert error_of(throttled)["code"] == "throttled"
    assert int(throttled["Retry-After"]) > 0
    assert post(HEATMAP, HEATMAP_BODY).status_code == 200  # separate limit per endpoint
    cache.clear()


def test_forecast_cache_is_sized_for_large_trips(settings):
    assert settings.CACHES["default"]["OPTIONS"]["MAX_ENTRIES"] >= 5000


def test_factory_selects_here_weather(settings):
    from routing.providers.cache import CachedForecaster
    from routing.providers.factory import get_forecaster

    settings.WEATHER_PROVIDER = "here"
    forecaster = get_forecaster()
    assert isinstance(forecaster, CachedForecaster)
    assert forecaster.description == "HERE Destination Weather hourly forecast"


def test_response_names_the_weather_source(providers):
    assert post(EVALUATE, VALID).json()["provider"]["weather"] == "Fake hourly forecast"


def test_factory_reuses_adapters_for_the_same_configuration(settings):
    from routing.providers.factory import get_forecaster, get_geocoder, get_router

    settings.WEATHER_PROVIDER = "here"
    assert get_forecaster() is get_forecaster()
    assert get_router() is get_router()
    assert get_geocoder() is get_geocoder()
    settings.HERE_WEATHER_CONCURRENCY = 3  # a different configuration gets its own adapter
    assert get_forecaster() is not factory_forecaster_before(settings)


def factory_forecaster_before(settings):
    from routing.providers.factory import get_forecaster

    settings.HERE_WEATHER_CONCURRENCY = 12
    return get_forecaster()


def test_identical_trip_is_served_from_the_response_cache(providers):
    first = post(EVALUATE, VALID).json()
    calls = len(providers["router"].calls)
    second = post(EVALUATE, VALID).json()
    assert second == first
    assert len(providers["router"].calls) == calls  # no provider work the second time
    post(EVALUATE, {**VALID, "load_weight_lb": 20_000})  # a different trip is computed
    assert len(providers["router"].calls) == calls + 1
