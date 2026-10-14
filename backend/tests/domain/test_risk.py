import pytest

from routing.domain.risk import assess, classify_rain, classify_snow, classify_wind, load_adjusted_severity
from routing.domain.types import Severity, WeatherSample

L, M, H, S, NT = Severity.LOW, Severity.MODERATE, Severity.HIGH, Severity.SEVERE, Severity.NO_TRAVEL


@pytest.mark.parametrize(
    ("mph", "expected"),
    [(0, L), (24.99, L), (25, M), (34.99, M), (35, H), (44.99, H), (45, S), (54.99, S), (55, NT), (80, NT)],
)
def test_wind_thresholds(mph, expected):
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    ("in_hr", "expected"),
    [(0, L), (0.099, L), (0.10, M), (0.249, M), (0.25, H), (0.499, H), (0.50, S), (1.00, S), (1.001, NT)],
)
def test_rain_thresholds(in_hr, expected):
    assert classify_rain(in_hr) == expected


@pytest.mark.parametrize(
    ("in_hr", "expected"),
    [(0, L), (0.499, L), (0.5, M), (0.999, M), (1.0, H), (1.999, H), (2.0, S), (3.0, S), (3.001, NT)],
)
def test_snow_thresholds(in_hr, expected):
    assert classify_snow(in_hr) == expected


@pytest.mark.parametrize(
    ("mph", "load", "expected"),
    [
        (45, 30_000, None),  # exactly 30,000 lb: strict > does not apply
        (45, 30_001, NT),
        (54.99, 30_001, NT),
        (35, 40_000, None),  # exactly 40,000 lb
        (35, 40_001, S),
        (44.99, 40_001, S),
        (34.99, 40_001, None),  # below the 35 mph band
        (45, 40_001, NT),  # 45-54 band applies, not the Severe rule
        (55, 30_001, None),  # >=55 is No Travel via wind alone
    ],
)
def test_load_overrides(mph, load, expected):
    assert load_adjusted_severity(mph, load) == expected


def weather(wind=0.0, rain=0.0, snow=0.0):
    return WeatherSample(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow)


def test_final_risk_is_maximum_of_components():
    result = assess(weather(wind=10, rain=0.3, snow=2.5), load_lb=20_000)
    assert result.severity == S
    assert result.factors == ("snow",)


def test_low_risk_has_no_factors():
    assert assess(weather(), load_lb=10_000).severity == L
    assert assess(weather(), load_lb=10_000).factors == ()


def test_wind_55_is_no_travel_for_any_load():
    assert assess(weather(wind=55), load_lb=1).severity == NT
    assert assess(weather(wind=55), load_lb=1).factors == ("wind",)


def test_load_override_reports_wind_and_load():
    result = assess(weather(wind=45), load_lb=30_001)
    assert result.severity == NT
    assert result.factors == ("wind", "load")
    assert assess(weather(wind=45), load_lb=30_000).severity == S


def test_heavy_load_at_high_wind_is_at_least_severe():
    assert assess(weather(wind=35), load_lb=40_001).severity == S
    assert assess(weather(wind=35), load_lb=40_000).severity == H
    # Another variable can still push it to No Travel.
    assert assess(weather(wind=35, rain=1.5), load_lb=40_001).severity == NT


def test_load_and_weather_tie_lists_all_factors():
    result = assess(weather(wind=35, snow=2.0), load_lb=40_001)
    assert result.severity == S
    assert result.factors == ("snow", "wind", "load")


def test_missing_value_is_unknown_not_low():
    result = assess(WeatherSample(wind_mph=10, rain_in_hr=None, snow_in_hr=0), load_lb=10_000)
    assert result.severity is None


def test_missing_value_with_known_no_travel_is_still_no_travel():
    result = assess(WeatherSample(wind_mph=None, rain_in_hr=None, snow_in_hr=3.5), load_lb=10_000)
    assert result.severity == NT
    assert result.factors == ("snow",)


def test_missing_value_with_severe_is_unknown_because_it_could_be_worse():
    assert assess(WeatherSample(wind_mph=None, rain_in_hr=0.6, snow_in_hr=0), load_lb=10_000).severity is None
