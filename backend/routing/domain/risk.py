"""Weather and load risk classification.

Thresholds use half-open intervals (see CLAUDE.md): the brief's overlapping ranges such as rain "0.10–0.25"
and "0.25–0.50" are resolved so each boundary value belongs to the higher band, except that rain 1.00 and
snow 3.00 stay Severe because No Travel is defined as strictly greater. Values are compared exactly as
received; nothing is rounded before classification.
"""

from __future__ import annotations

from routing.domain.types import RiskAssessment, Severity, WeatherSample

# Lower bounds (inclusive) for Moderate, High, Severe and No Travel.
WIND_MPH_BOUNDS = (25.0, 35.0, 45.0, 55.0)
# Lower bounds (inclusive) for Moderate, High, Severe; No Travel is strictly above the last value.
RAIN_IN_HR_BOUNDS = (0.10, 0.25, 0.50)
RAIN_NO_TRAVEL_ABOVE = 1.00
SNOW_IN_HR_BOUNDS = (0.5, 1.0, 2.0)
SNOW_NO_TRAVEL_ABOVE = 3.0

LOAD_NO_TRAVEL_ABOVE_LB = 30_000.0  # applies at 45 <= wind < 55 mph
LOAD_SEVERE_ABOVE_LB = 40_000.0  # applies at 35 <= wind < 45 mph


def _band(value: float, lower_bounds: tuple[float, ...]) -> Severity:
    level = Severity.LOW
    for index, bound in enumerate(lower_bounds, start=1):
        if value >= bound:
            level = Severity(index)
    return level


def classify_wind(wind_mph: float) -> Severity:
    return _band(wind_mph, WIND_MPH_BOUNDS)


def classify_rain(rain_in_hr: float) -> Severity:
    if rain_in_hr > RAIN_NO_TRAVEL_ABOVE:
        return Severity.NO_TRAVEL
    return _band(rain_in_hr, RAIN_IN_HR_BOUNDS)


def classify_snow(snow_in_hr: float) -> Severity:
    if snow_in_hr > SNOW_NO_TRAVEL_ABOVE:
        return Severity.NO_TRAVEL
    return _band(snow_in_hr, SNOW_IN_HR_BOUNDS)


def load_adjusted_severity(wind_mph: float, load_lb: float) -> Severity | None:
    """Severity imposed by the load rules, or ``None`` when no load rule applies.

    Wind >= 55 mph is already No Travel via :func:`classify_wind` for every load.
    """
    wind_band = classify_wind(wind_mph)
    if wind_band == Severity.SEVERE and load_lb > LOAD_NO_TRAVEL_ABOVE_LB:
        return Severity.NO_TRAVEL
    if wind_band == Severity.HIGH and load_lb > LOAD_SEVERE_ABOVE_LB:
        return Severity.SEVERE
    return None


def assess(weather: WeatherSample, load_lb: float) -> RiskAssessment:
    """Final risk = max of wind, rain, snow and load-adjusted severities.

    Missing variables make the result unknown, unless a known variable already yields No Travel: an
    unknown value can only raise the risk, so No Travel is certain and must still be reported.
    """
    components: dict[str, Severity] = {}
    if weather.wind_mph is not None:
        components["wind"] = classify_wind(weather.wind_mph)
    if weather.rain_in_hr is not None:
        components["rain"] = classify_rain(weather.rain_in_hr)
    if weather.snow_in_hr is not None:
        components["snow"] = classify_snow(weather.snow_in_hr)

    load_severity = (
        load_adjusted_severity(weather.wind_mph, load_lb) if weather.wind_mph is not None else None
    )
    candidates = list(components.values()) + ([load_severity] if load_severity is not None else [])
    worst = max(candidates, default=None)

    if not weather.is_complete and worst != Severity.NO_TRAVEL:
        return RiskAssessment(severity=None, factors=())
    assert worst is not None  # complete weather always yields three components

    if worst == Severity.LOW:
        return RiskAssessment(severity=worst, factors=())
    factors = [name for name, severity in components.items() if severity == worst]
    if load_severity == worst:
        factors += [f for f in ("wind", "load") if f not in factors]
    return RiskAssessment(severity=worst, factors=tuple(factors))
