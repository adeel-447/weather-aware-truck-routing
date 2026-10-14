"""Outbound JSON GET with timeouts and conservative retries."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from routing.providers.errors import (
    ProviderConfigError,
    ProviderError,
    ProviderRateLimited,
    ProviderRequestRejected,
    ProviderTimeout,
    ProviderUnavailable,
)

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
BACKOFF_BASE_S = 0.5
MAX_RETRY_AFTER_S = 5.0


class JsonClient:
    def __init__(
        self,
        provider: str,
        connect_timeout_s: float,
        read_timeout_s: float,
        max_retries: int,
        session: requests.Session | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.provider = provider
        self.timeout = (connect_timeout_s, read_timeout_s)
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self._sleep = sleep

    def get(self, url: str, params: dict[str, str | int]) -> Any:
        attempt = 0
        while True:
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.Timeout as exc:
                if attempt < self.max_retries:
                    attempt = self._backoff(attempt, None)
                    continue
                raise ProviderTimeout(self.provider, "request timed out") from exc
            except requests.RequestException as exc:
                if attempt < self.max_retries:
                    attempt = self._backoff(attempt, None)
                    continue
                raise ProviderUnavailable(self.provider, "connection failed") from exc

            retry_after = response.headers.get("Retry-After")
            # 429 is retried only when the provider says when; blind retries just burn more quota.
            retryable = response.status_code in RETRYABLE_STATUS and (
                response.status_code != 429 or _short_retry_after(retry_after)
            )
            if retryable and attempt < self.max_retries:
                attempt = self._backoff(attempt, retry_after)
                continue
            return self._parse(response)

    def _backoff(self, attempt: int, retry_after: str | None) -> int:
        delay = BACKOFF_BASE_S * 2**attempt
        if retry_after and retry_after.isdigit():
            delay = min(float(retry_after), MAX_RETRY_AFTER_S)
        logger.warning("%s: retrying after %.1fs (attempt %d)", self.provider, delay, attempt + 1)
        self._sleep(delay)
        return attempt + 1

    def _parse(self, response: requests.Response) -> Any:
        status = response.status_code
        try:
            body = response.json()
        except ValueError:
            body = None
        if 200 <= status < 300:
            if body is None:
                raise ProviderError(self.provider, "response was not valid JSON")
            return body
        detail = _error_detail(body) or f"HTTP {status}"
        if status == 429:
            raise ProviderRateLimited(self.provider, detail)
        if status in (401, 403):
            raise ProviderConfigError(self.provider, f"credentials rejected ({detail})")
        if status in RETRYABLE_STATUS:
            raise ProviderUnavailable(self.provider, detail)
        if 400 <= status < 500:
            raise ProviderRequestRejected(self.provider, detail)
        raise ProviderError(self.provider, detail)


def _short_retry_after(value: str | None) -> bool:
    return value is not None and value.isdigit() and float(value) <= MAX_RETRY_AFTER_S


def _error_detail(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    for key in ("cause", "reason", "title", "error_description", "message"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    return None
