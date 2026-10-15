import pytest
import requests
import responses

from routing.providers.errors import (
    ProviderConfigError,
    ProviderRateLimited,
    ProviderRequestRejected,
    ProviderTimeout,
    ProviderUnavailable,
)

URL = "https://api.example.test/data"


@responses.activate
def test_retries_transient_errors_then_succeeds(client_factory, sleeps):
    responses.get(URL, status=503)
    responses.get(URL, status=429, headers={"Retry-After": "1"})
    responses.get(URL, json={"ok": True})
    assert client_factory().get(URL, {}) == {"ok": True}
    assert len(responses.calls) == 3
    assert sleeps == [0.5, 1.0]


@responses.activate
def test_gives_up_after_max_retries(client_factory):
    for _ in range(3):
        responses.get(URL, status=502)
    with pytest.raises(ProviderUnavailable):
        client_factory(max_retries=2).get(URL, {})
    assert len(responses.calls) == 3


@responses.activate
def test_rate_limit_without_short_retry_after_is_reported_not_retried(client_factory, sleeps):
    responses.get(URL, status=429, json={"error": True, "reason": "Minutely API request limit exceeded."})
    with pytest.raises(ProviderRateLimited, match="Minutely API request limit"):
        client_factory().get(URL, {})
    responses.get(URL, status=429, headers={"Retry-After": "120"})
    with pytest.raises(ProviderRateLimited):
        client_factory().get(URL, {})
    assert len(responses.calls) == 2
    assert sleeps == []


@responses.activate
def test_server_error_backoff_follows_retry_after_with_cap(client_factory, sleeps):
    responses.get(URL, status=503, headers={"Retry-After": "120"})
    responses.get(URL, json={})
    client_factory().get(URL, {})
    assert sleeps == [5.0]


@responses.activate
def test_client_errors_are_not_retried_and_keep_provider_detail(client_factory):
    responses.get(URL, status=400, json={"title": "Malformed request", "cause": "Invalid departureTime"})
    with pytest.raises(ProviderRequestRejected, match="Invalid departureTime"):
        client_factory().get(URL, {})
    assert len(responses.calls) == 1


@responses.activate
def test_auth_failure_is_a_config_error(client_factory):
    responses.get(URL, status=401, json={"error": "Unauthorized", "error_description": "apiKey invalid"})
    with pytest.raises(ProviderConfigError) as excinfo:
        client_factory().get(URL, {})
    assert excinfo.value.http_status == 503


@responses.activate
def test_timeout_is_retried_then_reported(client_factory):
    for _ in range(3):
        responses.get(URL, body=requests.Timeout())
    with pytest.raises(ProviderTimeout):
        client_factory().get(URL, {})
    assert len(responses.calls) == 3


@responses.activate
def test_error_message_never_includes_query_secrets(client_factory):
    responses.get(URL, body=requests.ConnectionError(f"failed {URL}?apiKey=SECRET"))
    with pytest.raises(ProviderUnavailable) as excinfo:
        client_factory(max_retries=0).get(URL, {"apiKey": "SECRET"})
    assert "SECRET" not in str(excinfo.value)


@responses.activate
def test_malformed_url_is_a_config_error_without_retry(client_factory, sleeps):
    with pytest.raises(ProviderConfigError, match="invalid provider URL"):
        client_factory().get("not-a-url", {})
    assert sleeps == []


@responses.activate
def test_tls_failure_is_not_retried(client_factory, sleeps):
    responses.get(URL, body=requests.exceptions.SSLError("certificate verify failed"))
    with pytest.raises(ProviderUnavailable, match="secure connection failed"):
        client_factory().get(URL, {})
    assert len(responses.calls) == 1
    assert sleeps == []


@responses.activate
def test_connection_errors_are_retried(client_factory, sleeps):
    responses.get(URL, body=requests.ConnectionError("reset"))
    responses.get(URL, json={"ok": True})
    assert client_factory().get(URL, {}) == {"ok": True}
    assert sleeps == [0.5]


@responses.activate
def test_call_budget_stops_retries(sleeps):
    from routing.providers.http import JsonClient

    clock = iter([0.0, 9.0])  # start, then 9 s elapsed after the first failed attempt
    client = JsonClient(
        "Test", 3.0, 10.0, max_retries=2, budget_s=20.0, sleep=sleeps.append, clock=lambda: next(clock)
    )
    responses.get(URL, body=requests.Timeout())
    with pytest.raises(ProviderTimeout):
        client.get(URL, {})
    assert len(responses.calls) == 1  # 9 s + 0.5 s backoff + 13 s timeouts would exceed 20 s


def test_each_thread_gets_its_own_session(client_factory):
    import threading

    client = client_factory()
    sessions = []
    threads = [threading.Thread(target=lambda: sessions.append(client.session)) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len({id(session) for session in sessions}) == 3
    assert client.session is client.session  # stable within a thread
