"""Build provider adapters from settings. Adapter names come from *_PROVIDER environment variables."""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from routing.providers.base import Forecaster, Geocoder, TruckRouter
from routing.providers.cache import CachedForecaster
from routing.providers.here import HereGeocoder, HereTruckRouter
from routing.providers.http import JsonClient
from routing.providers.open_meteo import OpenMeteoForecaster


def _client(provider: str) -> JsonClient:
    return JsonClient(
        provider=provider,
        connect_timeout_s=settings.PROVIDER_CONNECT_TIMEOUT_S,
        read_timeout_s=settings.PROVIDER_READ_TIMEOUT_S,
        max_retries=settings.PROVIDER_MAX_RETRIES,
        budget_s=settings.PROVIDER_CALL_BUDGET_S,
    )


def get_geocoder() -> Geocoder:
    if settings.GEOCODING_PROVIDER == "here":
        return HereGeocoder(
            _client("HERE"),
            settings.HERE_GEOCODING_BASE_URL,
            settings.HERE_API_KEY,
            settings.GEOCODE_COUNTRY_CODES,
        )
    raise ImproperlyConfigured(f"unknown GEOCODING_PROVIDER {settings.GEOCODING_PROVIDER!r}")


def get_router() -> TruckRouter:
    if settings.ROUTING_PROVIDER == "here":
        return HereTruckRouter(_client("HERE"), settings.HERE_ROUTING_BASE_URL, settings.HERE_API_KEY)
    raise ImproperlyConfigured(f"unknown ROUTING_PROVIDER {settings.ROUTING_PROVIDER!r}")


def get_forecaster() -> Forecaster:
    if settings.WEATHER_PROVIDER == "open-meteo":
        inner = OpenMeteoForecaster(
            _client("Open-Meteo"), settings.OPEN_METEO_BASE_URL, settings.OPEN_METEO_API_KEY
        )
        return CachedForecaster(inner, cache, timeout_s=settings.CACHE_TIMEOUT_S)
    raise ImproperlyConfigured(f"unknown WEATHER_PROVIDER {settings.WEATHER_PROVIDER!r}")
