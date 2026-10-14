from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from routing.domain.eta import TimingCurve, arrival_at
from routing.domain.forecast import HourlyForecast, weather_at

CHICAGO = ZoneInfo("America/Chicago")


def test_segment_curve_uses_provider_durations_not_average_speed():
    # 60 mi of highway in 1 h, then 10 mi of city in 1 h.
    curve = TimingCurve.from_segments([(60.0, 3600.0), (10.0, 3600.0)], total_miles=70.0)
    assert curve.method == "provider_segments"
    assert curve.elapsed_at(30.0) == pytest.approx(1800.0)
    assert curve.elapsed_at(60.0) == pytest.approx(3600.0)
    assert curve.elapsed_at(65.0) == pytest.approx(5400.0)
    assert curve.elapsed_at(70.0) == pytest.approx(7200.0)
    proportional = TimingCurve.proportional(70.0, 7200.0)
    assert proportional.elapsed_at(30.0) == pytest.approx(7200.0 * 30 / 70)


def test_segment_curve_rescales_lengths_to_route_total():
    curve = TimingCurve.from_segments([(50.0, 1000.0), (50.0, 1000.0)], total_miles=200.0)
    assert curve.elapsed_at(100.0) == pytest.approx(1000.0)


def test_zero_length_segment_uses_earliest_arrival_at_that_point():
    curve = TimingCurve.from_segments([(10.0, 600.0), (0.0, 1800.0), (10.0, 600.0)], total_miles=20.0)
    assert curve.elapsed_at(10.0) == pytest.approx(600.0)
    assert curve.elapsed_at(15.0) == pytest.approx(600.0 + 1800.0 + 300.0)


def test_curve_rejects_invalid_segments():
    with pytest.raises(ValueError):
        TimingCurve.from_segments([], 10.0)
    with pytest.raises(ValueError):
        TimingCurve.from_segments([(0.0, 10.0)], 10.0)
    with pytest.raises(ValueError):
        TimingCurve.from_segments([(5.0, -1.0)], 10.0)


def test_arrival_uses_elapsed_route_time_in_utc():
    departure = datetime(2026, 10, 20, 8, 0, tzinfo=CHICAGO)  # 13:00Z (CDT, UTC-5)
    curve = TimingCurve.proportional(100.0, 7200.0)
    assert arrival_at(departure, curve, 50.0) == datetime(2026, 10, 20, 14, 0, tzinfo=UTC)


def test_arrival_across_dst_end_counts_real_elapsed_time():
    # 2026-11-01 00:30 CDT (05:30Z). Clocks fall back at 02:00 CDT to 01:00 CST.
    departure = datetime(2026, 11, 1, 0, 30, tzinfo=CHICAGO)
    curve = TimingCurve.proportional(100.0, 7200.0)
    eta = arrival_at(departure, curve, 100.0)
    assert eta == datetime(2026, 11, 1, 7, 30, tzinfo=UTC)
    local = eta.astimezone(CHICAGO)
    assert (local.hour, local.minute, local.tzname()) == (1, 30, "CST")  # naive local math would say 02:30


def test_arrival_rejects_naive_departure():
    with pytest.raises(ValueError):
        arrival_at(datetime(2026, 10, 20, 8, 0), TimingCurve.proportional(1.0, 1.0), 0.5)  # noqa: DTZ001


T0 = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def forecast(wind, rain, snow):
    times = tuple(T0 + timedelta(hours=i) for i in range(len(wind)))
    return HourlyForecast(times=times, wind_mph=tuple(wind), rain_in_hr=tuple(rain), snow_in_hr=tuple(snow))


SERIES = forecast(wind=[10.0, 30.0, 50.0], rain=[0.0, 0.2, 0.6], snow=[0.1, 0.0, 2.5])


def test_wind_exact_hour_and_interpolated_between_hours():
    assert weather_at(SERIES, T0 + timedelta(hours=1)).wind_mph == 30.0
    assert weather_at(SERIES, T0 + timedelta(minutes=90)).wind_mph == pytest.approx(40.0)


def test_precipitation_uses_bucket_containing_the_instant():
    # The bucket stamped 13:00 covers (12:00, 13:00].
    assert weather_at(SERIES, T0 + timedelta(hours=1)).rain_in_hr == 0.2
    assert weather_at(SERIES, T0 + timedelta(minutes=61)).rain_in_hr == 0.6
    assert weather_at(SERIES, T0 + timedelta(minutes=30)).rain_in_hr == 0.2  # not interpolated
    assert weather_at(SERIES, T0 + timedelta(minutes=90)).snow_in_hr == 2.5


def test_instant_outside_coverage_is_unavailable():
    after = weather_at(SERIES, T0 + timedelta(hours=2, minutes=1))
    assert (after.wind_mph, after.rain_in_hr, after.snow_in_hr) == (None, None, None)
    before = weather_at(SERIES, T0 - timedelta(minutes=30))
    assert before.wind_mph is None  # no instantaneous value before the first hour
    assert before.rain_in_hr == 0.0  # still inside the first bucket's preceding-hour window
    assert not before.is_complete


def test_null_values_stay_unavailable():
    series = forecast(wind=[10.0, None], rain=[0.0, None], snow=[0.0, 0.0])
    sample = weather_at(series, T0 + timedelta(minutes=30))
    assert sample.wind_mph is None
    assert sample.rain_in_hr is None
    assert sample.snow_in_hr == 0.0


def test_forecast_converts_non_utc_instants():
    local = (T0 + timedelta(hours=1)).astimezone(CHICAGO)
    assert weather_at(SERIES, local).wind_mph == 30.0


def test_forecast_validates_series():
    with pytest.raises(ValueError):
        HourlyForecast(times=(T0,), wind_mph=(1.0, 2.0), rain_in_hr=(0.0,), snow_in_hr=(0.0,))
    with pytest.raises(ValueError):
        HourlyForecast(
            times=(T0, T0 + timedelta(hours=2)),
            wind_mph=(1.0, 2.0),
            rain_in_hr=(0.0, 0.0),
            snow_in_hr=(0.0, 0.0),
        )
