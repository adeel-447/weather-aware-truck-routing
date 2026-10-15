import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    """Isolate tests: results, routes and forecasts are cached across requests in the app."""
    cache.clear()
    yield
    cache.clear()
