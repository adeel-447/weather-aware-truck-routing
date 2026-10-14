import json
from pathlib import Path
from typing import Any

import pytest

from routing.providers.http import JsonClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def client_factory(sleeps):
    def make(provider: str = "Test", max_retries: int = 2) -> JsonClient:
        return JsonClient(provider, 1.0, 1.0, max_retries, sleep=sleeps.append)

    return make
