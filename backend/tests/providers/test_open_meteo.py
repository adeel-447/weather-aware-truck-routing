import copy
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from django.core.cache import caches

from routing.domain.forecast import HourlyForecast
from routing.providers.cache import CachedForecaster, hours_bucket, snap
from routing.providers.errors import ProviderError, ProviderRequestRejected
from routing.providers.open_meteo import OpenMeteoForecaster
from tests.providers.conftest import load_fixture

URL = "https://weather.test/v1/forecast"
RECORDED = load_fixture("open_meteo_two_locations.json")  # live response recorded 2026-10-14


def forecaster(client_factory):
    return OpenMeteoForecaster(client_factory("Open-Meteo"), URL)


def query(call):
    return {k: v[0] for k, v in parse_qs(urlparse(call.request.url).query).items()}


@responses.activate
def test_parses_recorded_response_into_utc_hourly_series(client_factory):
    responses.get(URL, json=RECORDED)
    chicago, denver = forecaster(client_factory).hourly_forecasts([(41.88, -87.63), (39.74, -104.99)], 72)
    assert len(chicago.times) == 72
    assert chicago.times[0] == datetime.fromtimestamp(RECORDED[0]["hourly"]["time"][0], UTC)
    assert all(b - a == timedelta(hours=1) for a, b in zip(chicago.times, chicago.times[1:], strict=False))
    assert chicago.wind_mph[0] == RECORDED[0]["hourly"]["wind_speed_10m"][0]
    assert denver.snow_in_hr == tuple(RECORDED[1]["hourly"]["snowfall"])


@responses.activate
def test_request_parameters_fix_units_and_timezone(client_factory):
    responses.get(URL, json=RECORDED)
    forecaster(client_factory).hourly_forecasts([(41.88, -87.63), (39.74, -104.99)], 50)
    params = query(responses.calls[0])
    assert params["latitude"] == "41.8800,39.7400"
    assert params["longitude"] == "-87.6300,-104.9900"
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert params["timezone"] == "GMT"
    assert params["timeformat"] == "unixtime"
    assert params["past_hours"] == "2"
    assert params["forecast_hours"] == "50"
    assert params["hourly"] == "wind_speed_10m,rain,showers,snowfall"


@responses.activate
def test_rain_combines_rain_and_showers_and_keeps_nulls(client_factory):
    body = copy.deepcopy(RECORDED[0])
    body["hourly"]["rain"][:3] = [0.1, None, 0.0]
    body["hourly"]["showers"][:3] = [0.05, 0.2, None]
    body["hourly"]["wind_speed_10m"][0] = None
    responses.get(URL, json=body)  # single location -> object, not list
    (result,) = forecaster(client_factory).hourly_forecasts([(41.88, -87.63)], 72)
    assert result.rain_in_hr[0] == pytest.approx(0.15)
    assert result.rain_in_hr[1:3] == (None, None)
    assert result.wind_mph[0] is None


@responses.activate
def test_unexpected_units_are_rejected(client_factory):
    body = copy.deepcopy(RECORDED[0])
    body["hourly_units"]["snowfall"] = "cm"
    responses.get(URL, json=body)
    with pytest.raises(ProviderError, match="snowfall"):
        forecaster(client_factory).hourly_forecasts([(41.88, -87.63)], 72)


@responses.activate
def test_out_of_range_request_is_reported(client_factory):
    responses.get(
        URL, status=400, json={"error": True, "reason": "Parameter 'end_hour' is out of allowed range"}
    )
    with pytest.raises(ProviderRequestRejected, match="out of allowed range"):
        forecaster(client_factory).hourly_forecasts([(41.88, -87.63)], 72)


@responses.activate
def test_large_requests_are_chunked(client_factory):
    def reply(request):
        count = len(parse_qs(urlparse(request.url).query)["latitude"][0].split(","))
        return 200, {}, json.dumps([RECORDED[0]] * count)

    responses.add_callback(responses.GET, URL, callback=reply)
    locations = [(30 + i * 0.1, -90.0) for i in range(150)]
    results = forecaster(client_factory).hourly_forecasts(locations, 72)
    assert len(results) == 150
    assert len(responses.calls) == 2


@responses.activate
def test_forecast_hours_capped_at_provider_maximum(client_factory):
    responses.get(URL, json=RECORDED[0])
    forecaster(client_factory).hourly_forecasts([(41.88, -87.63)], 1000)
    assert query(responses.calls[0])["forecast_hours"] == "384"


# --- caching -----------------------------------------------------------------------------------------


class CountingForecaster:
    description = "Counting forecaster"
    fixed_window = False

    def __init__(self):
        self.calls = []

    def hourly_forecasts(self, locations, forecast_hours):
        self.calls.append((list(locations), forecast_hours))
        t0 = datetime(2026, 10, 20, tzinfo=UTC)
        return [
            HourlyForecast(times=(t0,), wind_mph=(lat,), rain_in_hr=(0.0,), snow_in_hr=(0.0,))
            for lat, _ in locations
        ]


@pytest.fixture
def cache():
    backend = caches["default"]
    backend.clear()
    yield backend
    backend.clear()


def test_snap_and_bucket():
    assert snap((41.8812, -87.6321)) == (41.9, -87.65)
    assert (hours_bucket(49), hours_bucket(72), hours_bucket(100), hours_bucket(500)) == (72, 72, 168, 384)


def test_cache_dedupes_nearby_points_and_serves_repeats(cache):
    inner = CountingForecaster()
    now = datetime(2026, 10, 20, 12, 30, tzinfo=UTC)
    cached = CachedForecaster(inner, cache, timeout_s=60, now=lambda: now)

    first = cached.hourly_forecasts([(41.881, -87.632), (41.879, -87.628), (39.74, -104.99)], 49)
    assert inner.calls == [([(41.9, -87.65), (39.75, -105.0)], 72)]
    assert first[0] is first[1]  # same snapped grid cell

    cached.hourly_forecasts([(39.74, -104.99)], 60)
    assert len(inner.calls) == 1  # same hour and bucket: served from cache


def test_cache_refreshes_when_the_hour_changes(cache):
    inner = CountingForecaster()
    clock = [datetime(2026, 10, 20, 12, 59, tzinfo=UTC)]
    cached = CachedForecaster(inner, cache, timeout_s=3600, now=lambda: clock[0])
    cached.hourly_forecasts([(39.74, -104.99)], 49)
    clock[0] = datetime(2026, 10, 20, 13, 0, tzinfo=UTC)
    cached.hourly_forecasts([(39.74, -104.99)], 49)
    assert len(inner.calls) == 2
