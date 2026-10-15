"""HERE Routing API v8 (truck) and Geocoding & Search v7 adapters.

Request/response fields verified against the Routing v8 OpenAPI spec (v8.164.0): weights are integer
kilograms, lengths are metres, durations are seconds, span ``offset`` indexes the section's decoded
flexible polyline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import flexpolyline

from routing.domain.geometry import LatLon
from routing.domain.units import meters_to_miles
from routing.providers.base import GeocodedPlace, ProviderRoute
from routing.providers.errors import NoRouteFound, PlaceNotFound, ProviderConfigError, ProviderError
from routing.providers.http import JsonClient

PROVIDER = "HERE"


def _require_key(api_key: str) -> str:
    if not api_key:
        raise ProviderConfigError(PROVIDER, "HERE_API_KEY is not configured")
    return api_key


class HereGeocoder:
    def __init__(self, client: JsonClient, base_url: str, api_key: str, country_codes: str) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.country_codes = country_codes

    def geocode(self, query: str) -> GeocodedPlace:
        params: dict[str, str | int] = {"q": query, "limit": 1, "apiKey": _require_key(self.api_key)}
        if self.country_codes:
            params["in"] = f"countryCode:{self.country_codes}"
        body = self.client.get(f"{self.base_url}/geocode", params)
        items = body.get("items") if isinstance(body, dict) else None
        if not items:
            raise PlaceNotFound(PROVIDER, f"no location found for '{query}'")
        item = items[0]
        try:
            position = item["position"]
            label = item.get("address", {}).get("label") or item.get("title") or query
            return GeocodedPlace(label=label, lat=float(position["lat"]), lon=float(position["lng"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(PROVIDER, "unexpected geocoding response") from exc


class HereTruckRouter:
    description = "HERE Routing API v8 (truck)"

    def __init__(self, client: JsonClient, base_url: str, api_key: str) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def truck_routes(
        self,
        origin: LatLon,
        destination: LatLon,
        departure: datetime,
        weight_kg: int,
        alternatives: int,
    ) -> list[ProviderRoute]:
        params: dict[str, str | int] = {
            "transportMode": "truck",
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{destination[0]},{destination[1]}",
            "departureTime": departure.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "alternatives": alternatives,
            "return": "polyline,summary",
            "spans": "duration,length",
            # Our weight is the actual loaded weight (empty truck + cargo); HERE defaults each of these
            # to the other when one is missing, so both carry the same value.
            "vehicle[grossWeight]": weight_kg,
            "vehicle[currentWeight]": weight_kg,
            "apiKey": _require_key(self.api_key),
        }
        body = self.client.get(f"{self.base_url}/routes", params)
        if not isinstance(body, dict):
            raise ProviderError(PROVIDER, "unexpected routing response")
        routes = body.get("routes") or []
        if not routes:
            notices = "; ".join(n.get("title", n.get("code", "")) for n in body.get("notices", []))
            raise NoRouteFound(PROVIDER, notices or "no truck route found")
        try:
            return [_parse_route(route, index) for index, route in enumerate(routes)]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(PROVIDER, "unexpected routing response") from exc


def _critical_notices(item: dict[str, Any]) -> list[str]:
    return [
        notice.get("title") or notice.get("code", "unknown notice")
        for notice in item.get("notices", [])
        if notice.get("severity", "critical") == "critical"
    ]


def _parse_route(route: dict[str, Any], index: int) -> ProviderRoute:
    points: list[LatLon] = []
    segments: list[tuple[float, float]] = []
    spans_usable = True
    total_m = 0.0
    total_s = 0.0
    notices = _critical_notices(route)

    for section in route["sections"]:
        section_points = [(float(p[0]), float(p[1])) for p in flexpolyline.decode(section["polyline"])]
        summary = section["summary"]
        length_m = float(summary["length"])
        duration_s = float(summary["duration"])
        total_m += length_m
        total_s += duration_s
        notices += _critical_notices(section)

        section_segments = _span_segments(section.get("spans"), len(section_points))
        if section_segments is None:
            spans_usable = False
        else:
            segments.extend(_reconcile(section_segments, duration_s))

        # Consecutive sections share their joint point.
        points.extend(section_points[1:] if points and section_points[0] == points[-1] else section_points)

    if len(points) < 2 or total_m <= 0:
        raise ValueError("route has no geometry")
    return ProviderRoute(
        route_id=chr(ord("A") + index) if index < 26 else str(index + 1),
        points=points,
        distance_miles=meters_to_miles(total_m),
        duration_seconds=total_s,
        timing_segments=segments if spans_usable and segments else None,
        notices=list(dict.fromkeys(notices)),
    )


def _span_segments(spans: Any, point_count: int) -> list[tuple[float, float]] | None:
    """(miles, seconds) per span, or None if spans are missing or malformed (proportional fallback)."""
    if not isinstance(spans, list) or not spans:
        return None
    segments = []
    for span in spans:
        try:
            offset = int(span["offset"])
            length_m = float(span["length"])
            duration_s = float(span["duration"])
        except (KeyError, TypeError, ValueError):
            return None
        if not 0 <= offset < point_count or length_m < 0 or duration_s < 0:
            return None
        segments.append((meters_to_miles(length_m), duration_s))
    return segments


def _reconcile(segments: list[tuple[float, float]], section_s: float) -> list[tuple[float, float]]:
    """Make a section's span time add up to its summary duration (the route's reported drive time).

    Pre/post actions (e.g. ferry boarding) are in the summary but not in spans: the shortfall becomes a
    stop at the section start. If spans add up to more than the summary, they are scaled down so ETAs,
    arrival time and duration stay consistent.
    """
    span_s = sum(seconds for _, seconds in segments)
    if span_s < section_s:
        return [(0.0, section_s - span_s), *segments]
    if span_s > section_s > 0:
        scale = section_s / span_s
        return [(miles, seconds * scale) for miles, seconds in segments]
    return segments
