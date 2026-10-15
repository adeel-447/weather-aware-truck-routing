"""Deployment settings: host and origin parsing from environment variables."""

import importlib
import os
import sys
from types import ModuleType
from unittest import mock


def load_settings(**env: str) -> ModuleType:
    base = {"DJANGO_DEBUG": "false", "DJANGO_SECRET_KEY": "test-key"}
    with mock.patch.dict(os.environ, {**base, **env}, clear=False):
        for key in ("RENDER_EXTERNAL_HOSTNAME", "DJANGO_ALLOWED_HOSTS", "CORS_ALLOWED_ORIGINS"):
            if key not in env:
                os.environ.pop(key, None)
        sys.modules.pop("config.settings", None)
        return importlib.import_module("config.settings")


def test_render_hostname_is_allowed_automatically():
    settings = load_settings(
        DJANGO_ALLOWED_HOSTS="weather-aware-truck-routing.onrender.com",
        RENDER_EXTERNAL_HOSTNAME="weather-aware-truck-routing-ypg8.onrender.com",
    )
    assert "weather-aware-truck-routing-ypg8.onrender.com" in settings.ALLOWED_HOSTS


def test_hosts_written_as_urls_are_reduced_to_host_names():
    settings = load_settings(
        DJANGO_ALLOWED_HOSTS="https://api.example.com/, other.example.com",
    )
    assert settings.ALLOWED_HOSTS == ["api.example.com", "other.example.com"]


def test_cors_origins_drop_trailing_slash():
    settings = load_settings(CORS_ALLOWED_ORIGINS="https://app.vercel.app/")
    assert settings.CORS_ALLOWED_ORIGINS == ["https://app.vercel.app"]


def test_unknown_hosts_still_rejected_without_render_variable():
    settings = load_settings(DJANGO_ALLOWED_HOSTS="api.example.com")
    assert settings.ALLOWED_HOSTS == ["api.example.com"]
