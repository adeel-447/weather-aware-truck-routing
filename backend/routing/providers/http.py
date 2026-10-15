"""Outbound JSON GET with timeouts and conservative retries."""

from __future__ import annotations

import logging
import threading
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
    """JSON GET with timeouts and conservative retries.

    Retried: timeouts, connection failures, 5xx, and 429 with a short Retry-After. Not retried: other
    4xx, TLS failures and malformed URLs (configuration errors). Each call also has a total time budget
    so a slow provider cannot hold a request for (retries + 1) x timeouts.
    """

    def __init__(
        self,
        provider: str,
        connect_timeout_s: float,
        read_timeout_s: float,
        max_retries: int,
        budget_s: float = 20.0,
        session: requests.Session | None = None,
        sleep: Any = time.sleep,
        clock: Any = time.monotonic,
    ) -> None:
        self.provider = provider
        self.timeout = (connect_timeout_s, read_timeout_s)
        self.max_retries = max_retries
        self.budget_s = budget_s
        # requests.Session is not documented as thread-safe, and adapters fetch in parallel, so each
        # thread gets its own session (and connection pool). An injected session is used as-is.
        self._shared_session = session
        self._local = threading.local()
        self._sleep = sleep
        self._clock = clock

    @property
    def session(self) -> requests.Session:
        if self._shared_session is not None:
            return self._shared_session
        session: requests.Session | None = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        return session

    def get(self, url: str, params: dict[str, str | int]) -> Any:
        started = float(self._clock())
        attempt = 0
        while True:
            failure: ProviderError
            cause: requests.RequestException
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.Timeout as exc:
                failure, cause = ProviderTimeout(self.provider, "request timed out"), exc
            except (
                requests.exceptions.MissingSchema,
                requests.exceptions.InvalidSchema,
                requests.exceptions.InvalidURL,
            ) as exc:
                raise ProviderConfigError(self.provider, "invalid provider URL") from exc
            except requests.exceptions.SSLError as exc:  # a ConnectionError subclass, but not transient
                raise ProviderUnavailable(self.provider, "secure connection failed") from exc
            except requests.ConnectionError as exc:
                failure, cause = ProviderUnavailable(self.provider, "connection failed"), exc
            except requests.RequestException as exc:
                raise ProviderUnavailable(self.provider, "request failed") from exc
            else:
                retry_after = response.headers.get("Retry-After")
                # 429 is retried only when the provider says when; blind retries just burn more quota.
                retryable = response.status_code in RETRYABLE_STATUS and (
                    response.status_code != 429 or _short_retry_after(retry_after)
                )
                if retryable and self._may_retry(attempt, started, retry_after):
                    attempt = self._backoff(attempt, retry_after)
                    continue
                return self._parse(response)

            if self._may_retry(attempt, started, None):
                attempt = self._backoff(attempt, None)
                continue
            raise failure from cause

    def _delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after and retry_after.isdigit():
            return min(float(retry_after), MAX_RETRY_AFTER_S)
        return float(BACKOFF_BASE_S * 2**attempt)

    def _may_retry(self, attempt: int, started: float, retry_after: str | None) -> bool:
        """Retry only if another full attempt (backoff + timeouts) still fits in the call budget."""
        if attempt >= self.max_retries:
            return False
        worst_next = self._delay(attempt, retry_after) + sum(self.timeout)
        elapsed = float(self._clock()) - started
        return elapsed + worst_next <= self.budget_s

    def _backoff(self, attempt: int, retry_after: str | None) -> int:
        delay = self._delay(attempt, retry_after)
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
