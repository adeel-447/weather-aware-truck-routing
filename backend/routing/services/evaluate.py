"""Route evaluation: geocode -> truck routes -> ETA checkpoints -> forecast -> risk -> ranking.

Weather is fetched once for all checkpoints of all routes. If the weather provider fails, routes are
still returned with every checkpoint Unknown, so nothing is presented as safe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from routing.domain.checkpoints import build_checkpoints, sample_positions
from routing.domain.eta import TimingCurve, arrival_at
from routing.domain.forecast import HourlyForecast, forecast_hours_needed, weather_at
from routing.domain.geometry import LatLon
from routing.domain.ranking import RankedRoute, RouteScore, RouteStanding, recommend
from routing.domain.scoring import summarize
from routing.domain.types import Checkpoint, Severity, SeveritySummary, WeatherSample
from routing.domain.units import gross_weight_kg
from routing.providers.base import Forecaster, GeocodedPlace, Geocoder, ProviderRoute, TruckRouter
from routing.providers.errors import PlaceNotFound, ProviderError
from routing.services.serialization import iso_utc, round_or_none

logger = logging.getLogger(__name__)

LEGAL_GROSS_LIMIT_LB = 80_000
CORRIDOR_MAX_POINTS = 2000
CORRIDOR_MIN_STEP_MILES = 5.0
UNAVAILABLE = WeatherSample(None, None, None)

ASSUMPTIONS = (
    "ETAs are driving time from the routing provider; rest, fuel and hours-of-service stops are not modeled.",
    "Weather risk load rules use the entered cargo load; truck routing uses empty truck weight + cargo.",
    "Wind is sustained 10 m wind speed, interpolated between forecast hours; rain and snow are the "
    "forecast hour containing the ETA.",
    "Checkpoint risk applies to the route stretch between the midpoints to neighbouring checkpoints.",
    "Missing forecast data is Unknown, never Low; routes with Unknown miles are not recommended.",
)


@dataclass(frozen=True, slots=True)
class Place:
    query: str | None
    coordinates: LatLon | None


@dataclass(frozen=True, slots=True)
class TripRequest:
    origin: Place
    destination: Place
    departure: datetime  # aware
    timezone: str
    load_lb: float
    spacing_miles: int


@dataclass(frozen=True, slots=True)
class Providers:
    geocoder: Geocoder
    router: TruckRouter
    forecaster: Forecaster


@dataclass(frozen=True, slots=True)
class Settings:
    empty_truck_lb: float
    alternatives: int


class TripValidationError(ValueError):
    def __init__(self, message: str, fields: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.fields = fields  # request fields the error applies to, for inline display


def _resolve(place: Place, geocoder: Geocoder, field: str) -> GeocodedPlace:
    if place.coordinates is not None:
        lat, lon = place.coordinates
        return GeocodedPlace(label=f"{lat:.5f}, {lon:.5f}", lat=lat, lon=lon)
    assert place.query is not None
    try:
        return geocoder.geocode(place.query)
    except PlaceNotFound as exc:
        exc.field = field
        raise


def _dedupe(routes: list[ProviderRoute]) -> list[ProviderRoute]:
    seen: set[tuple[LatLon, ...]] = set()
    unique = []
    for route in routes:
        key = tuple((round(lat, 5), round(lon, 5)) for lat, lon in route.points)
        if key not in seen:
            seen.add(key)
            unique.append(route)
    return unique


def _timing(route: ProviderRoute) -> TimingCurve:
    if route.timing_segments:
        try:
            return TimingCurve.from_segments(route.timing_segments, route.distance_miles)
        except ValueError:
            logger.warning("route %s: unusable span timing, using proportional ETA", route.route_id)
    return TimingCurve.proportional(route.distance_miles, route.duration_seconds)


def _fetch_forecasts(
    forecaster: Forecaster, locations: list[LatLon], latest: datetime, now: datetime
) -> tuple[dict[LatLon, HourlyForecast], str | None]:
    try:
        series = forecaster.hourly_forecasts(locations, forecast_hours_needed(latest, now))
    except ProviderError as exc:
        logger.warning("weather unavailable: %s", exc)
        return {}, exc.message
    return dict(zip(locations, series, strict=True)), None


def _corridor(routes: list[ProviderRoute]) -> list[LatLon]:
    """Points along every route for the heatmap grid, at most CORRIDOR_MAX_POINTS in total.

    A route sampled at ``step`` yields at most distance/step + 2 points (origin and destination), so a
    step of total / (max - 2 * routes) keeps the sum within the cap without truncating any route's end.
    """
    total = sum(r.distance_miles for r in routes)
    step = max(CORRIDOR_MIN_STEP_MILES, total / (CORRIDOR_MAX_POINTS - 2 * len(routes)))
    points: list[LatLon] = []
    for route in routes:
        points.extend(p for _, p in sample_positions(route.points, route.distance_miles, step))
    return points


def evaluate_trip(
    trip: TripRequest, providers: Providers, settings: Settings, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    origin = _resolve(trip.origin, providers.geocoder, "origin")
    destination = _resolve(trip.destination, providers.geocoder, "destination")
    if (round(origin.lat, 4), round(origin.lon, 4)) == (round(destination.lat, 4), round(destination.lon, 4)):
        # Either input may be the wrong one, so the error is shown under both.
        raise TripValidationError(
            "origin and destination resolve to the same place", fields=("origin", "destination")
        )

    routing_weight_lb = settings.empty_truck_lb + trip.load_lb
    provider_routes = providers.router.truck_routes(
        (origin.lat, origin.lon),
        (destination.lat, destination.lon),
        trip.departure,
        gross_weight_kg(trip.load_lb, settings.empty_truck_lb),
        settings.alternatives,
    )
    routes = _dedupe(provider_routes)
    warnings: list[dict[str, Any]] = []
    requested = settings.alternatives + 1
    if len(routes) < requested:
        warnings.append(
            _warning(
                "fewer_routes_than_requested",
                f"The routing provider returned {len(routes)} distinct truck route(s) of {requested} "
                "requested. No alternatives were invented.",
            )
        )
    if routing_weight_lb > LEGAL_GROSS_LIMIT_LB:
        warnings.append(
            _warning(
                "gross_weight_over_legal_limit",
                f"Empty truck + cargo = {routing_weight_lb:,.0f} lb exceeds the common 80,000 lb US limit.",
            )
        )

    # Pass 1: positions (sampled once per route) and the latest ETA, so weather is fetched in one batch.
    timings = {r.route_id: _timing(r) for r in routes}
    positions = {r.route_id: sample_positions(r.points, r.distance_miles, trip.spacing_miles) for r in routes}
    locations = [position for route_positions in positions.values() for _, position in route_positions]
    latest = max(
        [trip.departure.astimezone(UTC)]
        + [arrival_at(trip.departure, timings[r.route_id], r.distance_miles) for r in routes]
    )
    forecasts, weather_error = _fetch_forecasts(
        providers.forecaster, list(dict.fromkeys(locations)), latest, now
    )
    if weather_error:
        warnings.append(
            _warning(
                "weather_unavailable", f"Weather forecast unavailable ({weather_error}); risk is Unknown."
            )
        )

    def lookup(lat: float, lon: float, eta: datetime) -> WeatherSample:
        forecast = forecasts.get((lat, lon))
        return weather_at(forecast, eta) if forecast else UNAVAILABLE

    # Pass 2: checkpoints, risk and mileage per route.
    evaluated = []
    for route in routes:
        checkpoints = build_checkpoints(
            positions[route.route_id],
            trip.departure,
            timings[route.route_id],
            lookup,
            trip.load_lb,
        )
        summary = summarize(checkpoints, route.distance_miles)
        evaluated.append((route, checkpoints, summary))
        warnings.extend(_route_warnings(route, timings[route.route_id], summary, weather_error is None))

    recommendation = recommend(
        [RouteScore(r.route_id, r.duration_seconds, summary) for r, _, summary in evaluated]
    )
    ranked = {item.route_id: item for item in recommendation.ranked}
    route_payloads = [
        _route_payload(
            route, timings[route.route_id], checkpoints, summary, trip.departure, ranked[route.route_id]
        )
        for route, checkpoints, summary in evaluated
    ]
    route_payloads.sort(key=lambda payload: payload["rank"])

    return {
        "request": {
            "origin": _place_payload(origin),
            "destination": _place_payload(destination),
            "departure_at": iso_utc(trip.departure),
            "timezone": trip.timezone,
            "load_weight_lb": trip.load_lb,
            "checkpoint_spacing_miles": trip.spacing_miles,
            "empty_truck_weight_lb": settings.empty_truck_lb,
            "routing_weight_lb": routing_weight_lb,
        },
        "recommendation": {
            "status": recommendation.status.value,
            "route_id": recommendation.recommended_route_id,
            "reason": recommendation.reason,
        },
        "routes": route_payloads,
        "warnings": warnings,
        "corridor": [[round(lon, 5), round(lat, 5)] for lat, lon in _corridor(routes)],
        "heatmap_reference_at": iso_utc(
            trip.departure.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        ),
        "provider": {
            "routing": "HERE Routing API v8 (truck)",
            "weather": "Open-Meteo hourly forecast",
            "routes_requested": requested,
            "routes_returned": len(provider_routes),
            "duplicates_removed": len(provider_routes) - len(routes),
        },
        "assumptions": list(ASSUMPTIONS),
        "generated_at": iso_utc(now),
    }


def _warning(code: str, message: str, route_id: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "route_id": route_id}


def _route_warnings(
    route: ProviderRoute, timing: TimingCurve, summary: SeveritySummary, weather_ok: bool
) -> list[dict[str, Any]]:
    rid = route.route_id
    warnings = []
    if summary.has_no_travel:
        warnings.append(
            _warning(
                "no_travel",
                f"Route {rid}: {summary.miles[Severity.NO_TRAVEL]:.1f} mi of No Travel conditions at the "
                "estimated arrival times.",
                rid,
            )
        )
    if weather_ok and not summary.is_verified:
        warnings.append(
            _warning(
                "partial_forecast",
                f"Route {rid}: forecast unavailable for {summary.unknown_miles:.1f} mi (beyond forecast "
                "range or missing values).",
                rid,
            )
        )
    if timing.method == "proportional":
        warnings.append(
            _warning(
                "eta_approximated",
                f"Route {rid}: provider segment timing unavailable; ETAs assume constant average speed.",
                rid,
            )
        )
    warnings.extend(_warning("provider_notice", f"Route {rid}: {notice}", rid) for notice in route.notices)
    return warnings


def _place_payload(place: GeocodedPlace) -> dict[str, Any]:
    return {"label": place.label, "lat": place.lat, "lon": place.lon}


def _checkpoint_payload(index: int, checkpoint: Checkpoint) -> dict[str, Any]:
    severity = checkpoint.risk.severity
    weather = checkpoint.weather
    return {
        "index": index,
        "distance_miles": round(checkpoint.distance_miles, 2),
        "lat": round(checkpoint.lat, 5),
        "lon": round(checkpoint.lon, 5),
        "eta": iso_utc(checkpoint.eta),
        "weather": {
            "wind_mph": round_or_none(weather.wind_mph, 1),
            "rain_in_hr": round_or_none(weather.rain_in_hr, 3),
            "snow_in_hr": round_or_none(weather.snow_in_hr, 3),
        },
        "severity": severity.label if severity is not None else "unknown",
        "severity_score": severity.value if severity is not None else None,
        "factors": list(checkpoint.risk.factors),
        "interval_start_miles": round(checkpoint.interval_start_miles, 3),
        "interval_end_miles": round(checkpoint.interval_end_miles, 3),
    }


def _route_payload(
    route: ProviderRoute,
    timing: TimingCurve,
    checkpoints: list[Checkpoint],
    summary: SeveritySummary,
    departure: datetime,
    ranked: RankedRoute,
) -> dict[str, Any]:
    severity_miles = {s.label: round(m, 2) for s, m in summary.miles.items()}
    severity_miles["unknown"] = round(summary.unknown_miles, 2)
    return {
        "id": route.route_id,
        "rank": ranked.rank,
        "standing": ranked.standing.value,
        "is_recommended": ranked.standing == RouteStanding.RECOMMENDED,
        "note": ranked.note,
        "eligible": not summary.has_no_travel,
        "verified": summary.is_verified,
        "distance_miles": round(route.distance_miles, 2),
        "duration_seconds": round(route.duration_seconds),
        "departure_at": iso_utc(departure),
        "arrival_at": iso_utc(arrival_at(departure, timing, route.distance_miles)),
        "eta_method": timing.method,
        "severity_miles": severity_miles,
        "weighted_average_risk": round_or_none(summary.weighted_average_risk, 3),
        "notices": route.notices,
        "geometry": {
            "type": "LineString",
            "coordinates": [[round(lon, 5), round(lat, 5)] for lat, lon in route.points],
        },
        "checkpoints": [_checkpoint_payload(i, c) for i, c in enumerate(checkpoints)],
    }
