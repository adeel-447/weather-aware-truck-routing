"""Build provider adapters from settings. Adapter names come from *_PROVIDER environment variables."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import cast

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from routing.providers.base import Forecaster, Geocoder, TruckRouter
from routing.providers.cache import CachedForecaster, CachedGeocoder, CachedRouter
from routing.providers.here import HereGeocoder, HereTruckRouter
from routing.providers.here_weather import HereWeatherForecaster
from routing.providers.http import JsonClient
from routing.providers.open_meteo import OpenMeteoForecaster

_instances: dict[tuple[object, ...], object] = {}
_lock = threading.Lock()


def _shared[T](key: tuple[object, ...], build: Callable[[], T]) -> T:
    """One adapter per configuration for the process lifetime, so HTTP connections and worker
    threads are reused across requests instead of re-created (and re-handshaken) every time."""
    with _lock:
        if key not in _instances:
            _instances[key] = build()
        return cast(T, _instances[key])  # stored by this key's own builder


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
        key = (
            "geocoder",
            "here",
            settings.HERE_GEOCODING_BASE_URL,
            settings.HERE_API_KEY,
            settings.GEOCODE_COUNTRY_CODES,
        )
        return _shared(
            key,
            lambda: CachedGeocoder(
                HereGeocoder(
                    _client("HERE"),
                    settings.HERE_GEOCODING_BASE_URL,
                    settings.HERE_API_KEY,
                    settings.GEOCODE_COUNTRY_CODES,
                ),
                cache,
            ),
        )
    raise ImproperlyConfigured(f"unknown GEOCODING_PROVIDER {settings.GEOCODING_PROVIDER!r}")


def get_router() -> TruckRouter:
    if settings.ROUTING_PROVIDER == "here":
        key = ("router", "here", settings.HERE_ROUTING_BASE_URL, settings.HERE_API_KEY)
        return _shared(
            key,
            lambda: CachedRouter(
                HereTruckRouter(_client("HERE"), settings.HERE_ROUTING_BASE_URL, settings.HERE_API_KEY),
                cache,
                timeout_s=settings.CACHE_TIMEOUT_S,
            ),
        )
    raise ImproperlyConfigured(f"unknown ROUTING_PROVIDER {settings.ROUTING_PROVIDER!r}")


def get_forecaster() -> Forecaster:
    if settings.WEATHER_PROVIDER == "open-meteo":
        key: tuple[object, ...] = (
            "forecaster",
            "open-meteo",
            settings.OPEN_METEO_BASE_URL,
            settings.OPEN_METEO_API_KEY,
        )
        return _shared(
            key,
            lambda: CachedForecaster(
                OpenMeteoForecaster(
                    _client("Open-Meteo"), settings.OPEN_METEO_BASE_URL, settings.OPEN_METEO_API_KEY
                ),
                cache,
                timeout_s=settings.CACHE_TIMEOUT_S,
            ),
        )
    if settings.WEATHER_PROVIDER == "here":
        key = (
            "forecaster",
            "here",
            settings.HERE_WEATHER_BASE_URL,
            settings.HERE_API_KEY,
            settings.HERE_WEATHER_CONCURRENCY,
            settings.HERE_WEATHER_DEADLINE_S,
        )
        return _shared(
            key,
            lambda: CachedForecaster(
                HereWeatherForecaster(
                    _client("HERE"),
                    settings.HERE_WEATHER_BASE_URL,
                    settings.HERE_API_KEY,
                    concurrency=settings.HERE_WEATHER_CONCURRENCY,
                    deadline_s=settings.HERE_WEATHER_DEADLINE_S,
                ),
                cache,
                timeout_s=settings.CACHE_TIMEOUT_S,
            ),
        )
    raise ImproperlyConfigured(f"unknown WEATHER_PROVIDER {settings.WEATHER_PROVIDER!r}")
