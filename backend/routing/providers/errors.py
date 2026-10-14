"""Typed provider failures. Views map ``http_status`` to the API response; messages never contain secrets."""

from __future__ import annotations


class ProviderError(Exception):
    http_status = 502
    code = "provider_error"

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.message = message


class ProviderConfigError(ProviderError):
    """Missing or rejected credentials / misconfiguration on our side."""

    http_status = 503
    code = "provider_not_configured"


class ProviderUnavailable(ProviderError):
    """Timeouts, connection failures, rate limits and 5xx after retries."""

    http_status = 503
    code = "provider_unavailable"


class ProviderRateLimited(ProviderUnavailable):
    """HTTP 429: the provider's request quota is exhausted for now."""

    code = "provider_rate_limited"


class ProviderTimeout(ProviderUnavailable):
    http_status = 504
    code = "provider_timeout"


class ProviderRequestRejected(ProviderError):
    """The provider rejected the request (4xx other than auth), e.g. weight limit or out-of-range time."""

    http_status = 422
    code = "provider_rejected_request"


class NoRouteFound(ProviderError):
    http_status = 422
    code = "no_route_found"


class PlaceNotFound(ProviderError):
    http_status = 422
    code = "place_not_found"
