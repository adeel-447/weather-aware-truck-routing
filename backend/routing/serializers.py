"""Request validation for the API. Responses are plain dicts built by the services."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from routing.domain.geometry import LatLon
from routing.domain.sampling import ALLOWED_SPACINGS_MILES
from routing.services.evaluate import Place

MAX_LOAD_LB = 80_000
DEPARTURE_PAST_GRACE = timedelta(hours=1)
DEPARTURE_MAX_AHEAD = timedelta(days=14)
CORRIDOR_MAX_POINTS = 2000
COORDINATES = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def _now() -> datetime:
    return datetime.now(UTC)


def parse_place(value: str) -> Place:
    """'lat,lon' is used directly; anything else is geocoded."""
    match = COORDINATES.match(value)
    if not match:
        return Place(query=value.strip(), coordinates=None)
    lat, lon = float(match.group(1)), float(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise serializers.ValidationError("coordinates out of range; use 'lat,lon'")
    return Place(query=None, coordinates=(lat, lon))


def localize(value: str, timezone: ZoneInfo) -> tuple[datetime, bool]:
    """Parse ISO-8601. With an offset it is used as-is; without one it is local time in ``timezone``.

    Returns (aware datetime, ambiguous). Local times skipped by a DST jump are rejected; times repeated
    when clocks fall back resolve to the first occurrence and are flagged as ambiguous.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise serializers.ValidationError("must be an ISO-8601 date-time") from exc
    if parsed.tzinfo is not None:
        return parsed, False
    first, second = parsed.replace(tzinfo=timezone, fold=0), parsed.replace(tzinfo=timezone, fold=1)
    if first.astimezone(UTC).astimezone(timezone).replace(tzinfo=None) != parsed:
        raise serializers.ValidationError("this local time does not exist (daylight-saving clock change)")
    return first, first.utcoffset() != second.utcoffset()


class EvaluateRequestSerializer(serializers.Serializer[dict[str, Any]]):
    origin = serializers.CharField(max_length=200)
    destination = serializers.CharField(max_length=200)
    departure_at = serializers.CharField(max_length=40)
    timezone = serializers.CharField(max_length=64, default="UTC")
    load_weight_lb = serializers.FloatField(min_value=1, max_value=MAX_LOAD_LB)
    checkpoint_spacing_miles = serializers.ChoiceField(choices=ALLOWED_SPACINGS_MILES)

    def validate_origin(self, value: str) -> Place:
        return parse_place(value)

    def validate_destination(self, value: str) -> Place:
        return parse_place(value)

    def validate_timezone(self, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise serializers.ValidationError("unknown IANA timezone") from exc
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        try:
            departure, ambiguous = localize(attrs["departure_at"], ZoneInfo(attrs["timezone"]))
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"departure_at": exc.detail}) from exc
        now = _now()
        if departure < now - DEPARTURE_PAST_GRACE:
            raise serializers.ValidationError({"departure_at": "departure is in the past"})
        if departure > now + DEPARTURE_MAX_AHEAD:
            raise serializers.ValidationError(
                {"departure_at": "departure must be within 14 days (forecast range)"}
            )
        origin, destination = attrs["origin"], attrs["destination"]
        if origin == destination:
            raise serializers.ValidationError({"destination": "destination must differ from origin"})
        attrs["departure_at"] = departure
        attrs["departure_ambiguous"] = ambiguous
        attrs["checkpoint_spacing_miles"] = int(attrs["checkpoint_spacing_miles"])
        return attrs


class HeatmapRequestSerializer(serializers.Serializer[dict[str, Any]]):
    corridor = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
        min_length=1,
        max_length=CORRIDOR_MAX_POINTS,
        help_text="[[lon, lat], ...] as returned by the evaluate endpoint",
    )
    reference_at = serializers.DateTimeField()
    load_weight_lb = serializers.FloatField(min_value=1, max_value=MAX_LOAD_LB)

    def validate_corridor(self, value: list[list[float]]) -> list[LatLon]:
        points = []
        for lon, lat in value:
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise serializers.ValidationError("coordinates out of range; expected [lon, lat]")
            points.append((lat, lon))
        return points

    def validate_reference_at(self, value: datetime) -> datetime:
        now = _now()
        if value < now - DEPARTURE_PAST_GRACE - timedelta(hours=1) or value > now + DEPARTURE_MAX_AHEAD:
            raise serializers.ValidationError("reference time must be between now and 14 days ahead")
        return value
