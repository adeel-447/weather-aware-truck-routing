from django.http import HttpRequest, JsonResponse
from django.urls import path
from django.views.decorators.http import require_GET

from routing.views import EvaluateRoutesView, HeatmapView


@require_GET
def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health, name="health"),
    path("routes/evaluate/", EvaluateRoutesView.as_view(), name="evaluate-routes"),
    path("heatmap/", HeatmapView.as_view(), name="heatmap"),
]
