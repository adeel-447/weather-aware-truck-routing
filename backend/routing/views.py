from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.cache import cache
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from routing.providers import factory
from routing.serializers import EvaluateRequestSerializer, HeatmapRequestSerializer
from routing.services.evaluate import Providers, Settings, TripRequest, evaluate_trip
from routing.services.heatmap import corridor_heatmap


class EvaluateRoutesView(APIView):
    throttle_scope = "evaluate"

    def post(self, request: Request) -> Response:
        serializer = EvaluateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        trip = TripRequest(
            origin=data["origin"],
            destination=data["destination"],
            departure=data["departure_at"],
            timezone=data["timezone"],
            load_lb=data["load_weight_lb"],
            spacing_miles=data["checkpoint_spacing_miles"],
            departure_ambiguous=data["departure_ambiguous"],
        )
        trip_settings = Settings(
            empty_truck_lb=settings.TRUCK_EMPTY_WEIGHT_LB, alternatives=settings.ROUTE_ALTERNATIVES
        )
        # An identical trip within the cache window returns the stored result: no provider calls
        # and no recomputation (CPU is the bottleneck on small instances once providers are cached).
        key = "evaluate:" + hashlib.sha256(repr((trip, trip_settings)).encode()).hexdigest()
        result = cache.get(key)
        if result is None:
            providers = Providers(factory.get_geocoder(), factory.get_router(), factory.get_forecaster())
            result = evaluate_trip(trip, providers, trip_settings)
            cache.set(key, result, timeout=settings.CACHE_TIMEOUT_S)
        return Response(result)


class HeatmapView(APIView):
    throttle_scope = "heatmap"

    def post(self, request: Request) -> Response:
        serializer = HeatmapRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            corridor_heatmap(
                data["corridor"],
                data["reference_at"],
                data["load_weight_lb"],
                factory.get_forecaster(),
                max_cells=settings.HEATMAP_MAX_CELLS,
            )
        )
