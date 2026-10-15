"""Typed API response payloads. These mirror ``frontend/src/types/api.ts``; change both together.

TypedDicts (rather than dataclasses) because the payloads are the JSON contract itself: mypy checks
every field the services build, and DRF renders them without a conversion step.
"""

from __future__ import annotations

from typing import Literal, TypedDict

EtaMethod = Literal["provider_segments", "proportional"]
LonLat = list[float]  # [lon, lat]


class PlacePayload(TypedDict):
    label: str
    lat: float
    lon: float


class WeatherPayload(TypedDict):
    wind_mph: float | None
    rain_in_hr: float | None
    snow_in_hr: float | None


class CheckpointPayload(TypedDict):
    index: int
    distance_miles: float
    lat: float
    lon: float
    eta: str
    weather: WeatherPayload
    severity: str
    severity_score: int | None
    factors: list[str]
    interval_start_miles: float
    interval_end_miles: float


class SeverityMilesPayload(TypedDict):
    low: float
    moderate: float
    high: float
    severe: float
    no_travel: float
    unknown: float


class GeometryPayload(TypedDict):
    type: Literal["LineString"]
    coordinates: list[LonLat]


class RoutePayload(TypedDict):
    id: str
    rank: int
    standing: str
    is_recommended: bool
    note: str
    eligible: bool
    verified: bool
    distance_miles: float
    duration_seconds: int
    departure_at: str
    arrival_at: str
    eta_method: EtaMethod
    severity_miles: SeverityMilesPayload
    weighted_average_risk: float | None
    notices: list[str]
    geometry: GeometryPayload
    checkpoints: list[CheckpointPayload]


class WarningPayload(TypedDict):
    code: str
    message: str
    route_id: str | None


class RequestEchoPayload(TypedDict):
    origin: PlacePayload
    destination: PlacePayload
    departure_at: str
    timezone: str
    load_weight_lb: float
    checkpoint_spacing_miles: int
    empty_truck_weight_lb: float
    routing_weight_lb: float


class RecommendationPayload(TypedDict):
    status: str
    route_id: str | None
    reason: str


class ProviderPayload(TypedDict):
    routing: str
    weather: str
    routes_requested: int
    routes_returned: int
    duplicates_removed: int


class EvaluatePayload(TypedDict):
    request: RequestEchoPayload
    recommendation: RecommendationPayload
    routes: list[RoutePayload]
    warnings: list[WarningPayload]
    corridor: list[LonLat]
    heatmap_reference_at: str
    provider: ProviderPayload
    assumptions: list[str]
    generated_at: str


class HeatmapFramePayload(TypedDict):
    offset_hours: int
    valid_at: str
    available: bool
    severity: list[int | None]
    wind_mph: list[float | None]
    rain_in_hr: list[float | None]
    snow_in_hr: list[float | None]


class UnitsPayload(TypedDict):
    wind_mph: str
    rain_in_hr: str
    snow_in_hr: str


class HeatmapPayload(TypedDict):
    layer: Literal["composite_severity"]
    severity_scale: dict[str, str]
    units: UnitsPayload
    note: str
    reference_at: str
    load_weight_lb: float
    cell_size_degrees: float
    cells: list[LonLat]
    frames: list[HeatmapFramePayload]
    generated_at: str
