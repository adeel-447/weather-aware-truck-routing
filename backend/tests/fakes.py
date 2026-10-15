"""In-memory provider fakes for service and API tests (no network)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from routing.domain.forecast import HourlyForecast
from routing.providers.base import GeocodedPlace, ProviderRoute
from routing.providers.errors import PlaceNotFound

SERIES_START = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)
SERIES_HOURS = 400

CHICAGO = (41.8800, -87.6300)
ROCKFORD = (42.2700, -89.0900)
JOLIET = (41.5250, -88.0817)

# (lat, lon, valid time) -> (wind mph, rain in/hr, snow in/hr); None values mean unavailable.
WeatherFn = Callable[[float, float, datetime], tuple[float | None, float | None, float | None]]


def calm(_lat: float, _lon: float, _at: datetime) -> tuple[float | None, float | None, float | None]:
    return (5.0, 0.0, 0.0)


class FakeGeocoder:
    def __init__(self, places: dict[str, GeocodedPlace] | None = None, error: Exception | None = None):
        self.places = places or {
            "Chicago, IL": GeocodedPlace("Chicago, IL, United States", *CHICAGO),
            "Rockford, IL": GeocodedPlace("Rockford, IL, United States", *ROCKFORD),
        }
        self.error = error
        self.queries: list[str] = []

    def geocode(self, query: str) -> GeocodedPlace:
        self.queries.append(query)
        if self.error:
            raise self.error
        if query not in self.places:
            raise PlaceNotFound("HERE", f"no location found for '{query}'")
        return self.places[query]


def straight_route(
    route_id: str,
    via: tuple[float, float],
    distance_miles: float,
    duration_seconds: float,
    segments: list[tuple[float, float]] | None = None,
    notices: list[str] | None = None,
) -> ProviderRoute:
    return ProviderRoute(
        route_id=route_id,
        points=[CHICAGO, via, ROCKFORD],
        distance_miles=distance_miles,
        duration_seconds=duration_seconds,
        timing_segments=segments,
        notices=notices or [],
    )


def three_routes() -> list[ProviderRoute]:
    return [
        straight_route("A", (42.05, -88.30), 90.0, 5400, segments=[(45.0, 2700), (45.0, 2700)]),
        straight_route("B", JOLIET, 120.0, 7200, segments=[(60.0, 3000), (60.0, 4200)]),
        straight_route("C", (42.40, -88.00), 110.0, 6600),
    ]


class FakeRouter:
    description = "Fake truck router"

    def __init__(self, routes: list[ProviderRoute] | None = None, error: Exception | None = None):
        self.routes = routes if routes is not None else three_routes()
        self.error = error
        self.calls: list[dict[str, object]] = []

    def truck_routes(self, origin, destination, departure, weight_kg, alternatives):
        self.calls.append(
            {
                "origin": origin,
                "destination": destination,
                "departure": departure,
                "weight_kg": weight_kg,
                "alternatives": alternatives,
            }
        )
        if self.error:
            raise self.error
        return self.routes


class FakeForecaster:
    description = "Fake hourly forecast"
    fixed_window = False

    def __init__(
        self,
        weather: WeatherFn = calm,
        error: Exception | None = None,
        start: datetime = SERIES_START,
        hours: int = SERIES_HOURS,
    ):
        self.weather = weather
        self.error = error
        self.start = start
        self.hours = hours
        self.calls: list[tuple[list[tuple[float, float]], int]] = []

    def hourly_forecasts(self, locations, forecast_hours):
        self.calls.append((list(locations), forecast_hours))
        if self.error:
            raise self.error
        times = tuple(self.start + timedelta(hours=i) for i in range(self.hours))
        result = []
        for lat, lon in locations:
            values = [self.weather(lat, lon, t) for t in times]
            result.append(
                HourlyForecast(
                    times=times,
                    wind_mph=tuple(v[0] for v in values),
                    rain_in_hr=tuple(v[1] for v in values),
                    snow_in_hr=tuple(v[2] for v in values),
                )
            )
        return result
