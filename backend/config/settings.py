"""Django settings. All deploy-specific values come from environment variables (see ../.env.example)."""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false")
    SECRET_KEY = secrets.token_urlsafe(50)  # ephemeral dev key; nothing is signed or persisted


def host_only(value: str) -> str:
    """Accept hosts written as URLs ("https://example.com/") and reduce them to "example.com"."""
    return value.split("://", 1)[-1].split("/", 1)[0]


def origin_only(value: str) -> str:
    """CORS origins are scheme + host with no path or trailing slash."""
    return value.rstrip("/")


ALLOWED_HOSTS = [host_only(h) for h in env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")]
# Render sets the service's real host name (it may carry a suffix such as "-ypg8"); trust it.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
CORS_ALLOWED_ORIGINS = [origin_only(o) for o in env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "corsheaders",
    "rest_framework",
    "routing",
]

# No CSRF/session/auth middleware: the API is stateless, unauthenticated JSON with no cookies.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Stateless API: no models are stored.
DATABASES: dict[str, dict[str, object]] = {}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "weather-routing",
        "TIMEOUT": int(os.environ.get("CACHE_TIMEOUT_S", "900")),
        # One entry per forecast grid cell: a long 3-route trip plus its heatmap is ~1,000 entries.
        "OPTIONS": {"MAX_ENTRIES": int(os.environ.get("CACHE_MAX_ENTRIES", "10000"))},
    }
}

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "routing.exceptions.api_exception_handler",
    # The endpoints are public and every call spends provider quota (HERE weather: one request per
    # location), so each client gets a per-endpoint rate limit. Counters live in the cache, i.e. per
    # gunicorn worker with LocMemCache: an approximate limit, not an exact one.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "evaluate": os.environ.get("THROTTLE_EVALUATE", "30/hour"),
        "heatmap": os.environ.get("THROTTLE_HEATMAP", "60/hour"),
    },
    # Proxies in front of the app (Render: 1). Unset = use the whole X-Forwarded-For value.
    "NUM_PROXIES": int(os.environ["NUM_PROXIES"]) if os.environ.get("NUM_PROXIES") else None,
}

USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- External providers -------------------------------------------------------
ROUTING_PROVIDER = os.environ.get("ROUTING_PROVIDER", "here")
GEOCODING_PROVIDER = os.environ.get("GEOCODING_PROVIDER", "here")
WEATHER_PROVIDER = os.environ.get("WEATHER_PROVIDER", "open-meteo")

HERE_API_KEY = os.environ.get("HERE_API_KEY", "")
HERE_ROUTING_BASE_URL = os.environ.get("HERE_ROUTING_BASE_URL", "https://router.hereapi.com/v8")
HERE_GEOCODING_BASE_URL = os.environ.get("HERE_GEOCODING_BASE_URL", "https://geocode.search.hereapi.com/v1")
ROUTE_ALTERNATIVES = int(os.environ.get("ROUTE_ALTERNATIVES", "2"))
GEOCODE_COUNTRY_CODES = os.environ.get("GEOCODE_COUNTRY_CODES", "USA")

# Routing weight = empty truck + cargo. Risk load rules use the cargo load only.
TRUCK_EMPTY_WEIGHT_LB = float(os.environ.get("TRUCK_EMPTY_WEIGHT_LB", "35000"))
CACHE_TIMEOUT_S = int(os.environ.get("CACHE_TIMEOUT_S", "900"))
# Heatmap grid cap. Each cell is one forecast location; Open-Meteo's free tier allows 600 per minute.
# HERE weather costs one request per cell, so it gets a smaller default grid than Open-Meteo.
HEATMAP_MAX_CELLS = int(os.environ.get("HEATMAP_MAX_CELLS", "80" if WEATHER_PROVIDER == "here" else "200"))
if HEATMAP_MAX_CELLS < 9:
    raise RuntimeError("HEATMAP_MAX_CELLS must be at least 9")

HERE_WEATHER_BASE_URL = os.environ.get("HERE_WEATHER_BASE_URL", "https://weather.hereapi.com/v3")
# Parallel requests, one location each (every worker thread has its own HTTP session).
HERE_WEATHER_CONCURRENCY = int(os.environ.get("HERE_WEATHER_CONCURRENCY", "12"))
# Overall limit for one batch of weather lookups; unfinished locations become Unknown.
HERE_WEATHER_DEADLINE_S = float(os.environ.get("HERE_WEATHER_DEADLINE_S", "60"))

OPEN_METEO_BASE_URL = os.environ.get("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1/forecast")
OPEN_METEO_API_KEY = os.environ.get("OPEN_METEO_API_KEY", "")

PROVIDER_CONNECT_TIMEOUT_S = float(os.environ.get("PROVIDER_CONNECT_TIMEOUT_S", "3"))
PROVIDER_READ_TIMEOUT_S = float(os.environ.get("PROVIDER_READ_TIMEOUT_S", "10"))
PROVIDER_MAX_RETRIES = int(os.environ.get("PROVIDER_MAX_RETRIES", "2"))
# Upper bound on one provider call including retries (a request may make several calls).
PROVIDER_CALL_BUDGET_S = float(os.environ.get("PROVIDER_CALL_BUDGET_S", "20"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
