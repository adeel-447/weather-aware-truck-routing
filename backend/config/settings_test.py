"""Settings for pytest and mypy: deterministic, no real credentials."""

import os

os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key")
os.environ.setdefault("HERE_API_KEY", "test-here-key")

from config.settings import *  # noqa: E402,F403
