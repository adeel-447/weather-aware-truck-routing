from __future__ import annotations

from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from routing.providers import factory
from routing.serializers import EvaluateRequestSerializer, HeatmapRequestSerializer
from routing.services.evaluate import Providers, Settings, TripRequest, evaluate_trip
from routing.services.heatmap import corridor_heatmap


class EvaluateRoutesView(APIView):
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
        )
        providers = Providers(factory.get_geocoder(), factory.get_router(), factory.get_forecaster())
        result = evaluate_trip(
            trip,
            providers,
            Settings(empty_truck_lb=settings.TRUCK_EMPTY_WEIGHT_LB, alternatives=settings.ROUTE_ALTERNATIVES),
        )
        if data["departure_ambiguous"]:
            result["warnings"].append(
                {
                    "code": "ambiguous_local_time",
                    "message": "Departure local time occurs twice (clocks fall back); the first occurrence "
                    "was used.",
                    "route_id": None,
                }
            )
        return Response(result)


class HeatmapView(APIView):
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
