import copy
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from django.core.cache import caches

from routing.domain.forecast import weather_at
from routing.providers.cache import CachedForecaster
from routing.providers.errors import ProviderConfigError, ProviderError, ProviderRateLimited
from routing.providers.here_weather import HereWeatherForecaster, parse_hourly
from tests.providers.conftest import load_fixture

URL = "https://weather.test/v3/report"
RECORDED = load_fixture("here_weather_hourly.json")  # live response recorded 2026-10-15, trimmed to 72 h


def items(body):
    return body["places"][0]["hourlyForecasts"][0]["forecasts"]


def forecaster(client_factory, key="k", concurrency=4):
    return HereWeatherForecaster(client_factory("HERE"), "https://weather.test/v3/", key, concurrency)


def query(call):
    return {k: v[0] for k, v in parse_qs(urlparse(call.request.url).query).items()}


def test_parses_recorded_response_to_utc_hourly_series():
    series = parse_hourly(RECORDED)
    first = items(RECORDED)[0]
    assert len(series.times) == 72
    assert series.times[0] == datetime.fromisoformat(first["time"]).astimezone(UTC)
    assert series.times[0].tzinfo == UTC
    assert all(b - a == timedelta(hours=1) for a, b in zip(series.times, series.times[1:], strict=False))
    assert series.wind_mph[0] == first["windSpeed"]  # mph with units=imperial


def test_precipitation_bucket_is_the_larger_of_the_two_neighbouring_hours():
    body = copy.deepcopy(RECORDED)
    hours = items(body)
    for item in hours[:4]:
        item["rainFall"], item["snowFall"] = 0, 0
    hours[1]["rainFall"] = 0.3  # one wet hour
    hours[2]["snowFall"] = 1.2
    series = parse_hourly(body)
    assert series.rain_in_hr[:4] == (0, 0.3, 0.3, 0)  # covers either hour convention
    assert series.snow_in_hr[:4] == (0, 0, 1.2, 1.2)
    # The domain reads the bucket at the first timestamp >= ETA, so an ETA after the wet hour's
    # timestamp still sees it.
    eta = series.times[1] + timedelta(minutes=30)
    assert weather_at(series, eta).rain_in_hr == 0.3


def test_missing_values_stay_unknown():
    body = copy.deepcopy(RECORDED)
    del items(body)[0]["windSpeed"]
    items(body)[3]["rainFall"] = None
    series = parse_hourly(body)
    assert series.wind_mph[0] is None
    assert series.rain_in_hr[3] is None and series.rain_in_hr[4] is None  # the next bucket too


@pytest.mark.parametrize(
    "body",
    [{}, {"places": []}, {"places": [{"hourlyForecasts": [{"forecasts": [{"time": "not a time"}]}]}]}],
)
def test_malformed_responses_are_provider_errors(body):
    with pytest.raises(ProviderError):
        parse_hourly(body)


@responses.activate
def test_requests_one_location_per_call_with_imperial_units(client_factory):
    responses.get(URL, json=RECORDED)
    result = forecaster(client_factory).hourly_forecasts([(41.88, -87.63), (39.74, -104.99)], 50)
    assert len(result) == 2
    params = sorted((query(call) for call in responses.calls), key=lambda p: p["location"])
    assert [p["location"] for p in params] == ["39.7400,-104.9900", "41.8800,-87.6300"]
    assert all(p["products"] == "forecastHourly" and p["units"] == "imperial" for p in params)
    assert all(p["apiKey"] == "k" for p in params)


@responses.activate
def test_results_keep_input_order_under_parallel_fetching(client_factory):
    def reply(request):
        lat = float(parse_qs(urlparse(request.url).query)["location"][0].split(",")[0])
        body = copy.deepcopy(RECORDED)
        items(body)[0]["windSpeed"] = lat  # tag each response with its latitude
        return 200, {}, json.dumps(body)

    responses.add_callback(responses.GET, URL, callback=reply)
    locations = [(30.0 + i, -90.0) for i in range(12)]
    result = forecaster(client_factory, concurrency=6).hourly_forecasts(locations, 50)
    assert [series.wind_mph[0] for series in result] == [lat for lat, _ in locations]


@responses.activate
def test_one_failed_location_becomes_unknown_not_an_error(client_factory):
    def reply(request):
        lat = parse_qs(urlparse(request.url).query)["location"][0].split(",")[0]
        if lat == "40.0000":
            return 400, {}, json.dumps({"title": "Bad location", "cause": "Bad location"})
        return 200, {}, json.dumps(RECORDED)

    responses.add_callback(responses.GET, URL, callback=reply)
    good, bad = forecaster(client_factory).hourly_forecasts([(41.0, -90.0), (40.0, -90.0)], 50)
    assert len(good.times) == 72
    assert bad.times == ()
    assert weather_at(bad, good.times[5]).wind_mph is None  # unknown, never Low


@responses.activate
def test_all_locations_failing_reports_the_provider_error(client_factory):
    responses.get(URL, status=429, json={"error": "Too Many Requests", "error_description": "quota"})
    with pytest.raises(ProviderRateLimited):
        forecaster(client_factory).hourly_forecasts([(41.0, -90.0), (40.0, -90.0)], 50)


def test_missing_key_fails_before_any_request(client_factory):
    with responses.RequestsMock() as mocked, pytest.raises(ProviderConfigError, match="HERE_API_KEY"):
        forecaster(client_factory, key="").hourly_forecasts([(41.0, -90.0)], 50)
    assert len(mocked.calls) == 0


@responses.activate
def test_failed_lookups_are_not_cached(client_factory):
    cache = caches["default"]
    cache.clear()
    responses.get(URL, status=400, json={"title": "Bad"})
    responses.get(URL, json=RECORDED)
    now = datetime(2026, 10, 15, 12, tzinfo=UTC)
    cached = CachedForecaster(forecaster(client_factory), cache, timeout_s=60, now=lambda: now)
    with pytest.raises(ProviderError):  # the only location failed
        cached.hourly_forecasts([(41.0, -90.0)], 50)
    assert len(cached.hourly_forecasts([(41.0, -90.0)], 50)[0].times) == 72  # retried, not cached
    assert cached.description == "HERE Destination Weather hourly forecast"
    cache.clear()


@responses.activate
def test_overall_deadline_turns_slow_locations_unknown(client_factory):
    import time

    def reply(request):
        lat = parse_qs(urlparse(request.url).query)["location"][0].split(",")[0]
        if lat == "40.0000":
            time.sleep(0.5)  # longer than the batch deadline
        return 200, {}, json.dumps(RECORDED)

    responses.add_callback(responses.GET, URL, callback=reply)
    slow = HereWeatherForecaster(client_factory("HERE"), "https://weather.test/v3", "k", 4, deadline_s=0.2)
    started = time.monotonic()
    fast, late = slow.hourly_forecasts([(41.0, -90.0), (40.0, -90.0)], 50)
    assert time.monotonic() - started < 0.45  # returned at the deadline, not after the slow call
    assert len(fast.times) == 72
    assert late.times == ()  # Unknown, never Low


@responses.activate
def test_deadline_with_nothing_finished_is_a_timeout(client_factory):
    import time

    from routing.providers.errors import ProviderTimeout

    def reply(request):
        time.sleep(0.4)
        return 200, {}, json.dumps(RECORDED)

    responses.add_callback(responses.GET, URL, callback=reply)
    slow = HereWeatherForecaster(client_factory("HERE"), "https://weather.test/v3", "k", 4, deadline_s=0.1)
    with pytest.raises(ProviderTimeout):
        slow.hourly_forecasts([(41.0, -90.0), (40.0, -90.0)], 50)


def test_fixed_window_provider_shares_cache_entries_across_horizons(client_factory):
    cache = caches["default"]
    cache.clear()
    calls = []

    class Fixed:
        description = "fixed"
        fixed_window = True

        def hourly_forecasts(self, locations, forecast_hours):
            calls.append(forecast_hours)
            return [parse_hourly(RECORDED) for _ in locations]

    now = datetime(2026, 10, 15, 12, tzinfo=UTC)
    cached = CachedForecaster(Fixed(), cache, timeout_s=60, now=lambda: now)
    cached.hourly_forecasts([(41.0, -90.0)], 130)  # route evaluation (bucket 168)
    cached.hourly_forecasts([(41.0, -90.0)], 200)  # heatmap (bucket 384)
    assert len(calls) == 1
    cache.clear()
