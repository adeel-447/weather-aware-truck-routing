"""One error envelope for every API failure: {"error": {"code", "message", "fields"?, "provider"?}}."""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from routing.providers.errors import PlaceNotFound, ProviderError
from routing.services.evaluate import TripValidationError

logger = logging.getLogger(__name__)


def error_response(http_status: int, code: str, message: str, **extra: Any) -> Response:
    return Response({"error": {"code": code, "message": message, **extra}}, status=http_status)


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, exceptions.ValidationError):
        return error_response(
            status.HTTP_400_BAD_REQUEST, "invalid_request", "Request validation failed.", fields=exc.detail
        )
    if isinstance(exc, TripValidationError):
        extra = {"fields": {field: [str(exc)] for field in exc.fields}} if exc.fields else {}
        return error_response(status.HTTP_400_BAD_REQUEST, "invalid_request", str(exc), **extra)
    if isinstance(exc, ProviderError):
        logger.warning("provider failure: %s", exc)
        extra = {}
        if isinstance(exc, PlaceNotFound) and exc.field:
            extra["fields"] = {exc.field: [exc.message]}
        return error_response(exc.http_status, exc.code, exc.message, provider=exc.provider, **extra)
    response = exception_handler(exc, context)
    if response is not None:
        detail = (
            response.data.get("detail", "Request failed.")
            if isinstance(response.data, dict)
            else "Request failed."
        )
        return error_response(response.status_code, getattr(exc, "default_code", "error"), str(detail))
    logger.exception("unhandled error")
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Unexpected server error.")
