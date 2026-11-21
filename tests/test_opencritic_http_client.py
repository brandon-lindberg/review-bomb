"""HTTP client reuse and network-retry behaviour for the OpenCritic service.

A sync run makes thousands of calls — the ID reconcile window alone walks 2,500
IDs — and `_request` used to build a fresh `httpx.AsyncClient` for every attempt
of every request, so each one paid a new DNS lookup, TCP connect and TLS
handshake. On 2026-09-08 that path met a runner whose name resolution had
dropped, and the retry policy (2s then 3s) gave up after five seconds.
"""

from typing import Any

import httpx
import pytest

from app.services import opencritic as opencritic_module
from app.services.opencritic import OpenCriticQuotaError, OpenCriticService


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    """`__init__` refuses to build without a key."""
    monkeypatch.setattr(
        opencritic_module.settings, "rapidapi_key", "test-key", raising=False
    )


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Retry backoff is asserted on, not waited through."""
    slept: list[float] = []

    async def _record(seconds):
        slept.append(seconds)

    monkeypatch.setattr(opencritic_module.asyncio, "sleep", _record)
    return slept


class RecordingTransport(httpx.AsyncBaseTransport):
    """Serves queued outcomes and counts how many connections were opened."""

    def __init__(self, outcomes: list[Any]):
        self._outcomes = list(outcomes)
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self._outcomes.pop(0) if self._outcomes else httpx.Response(200, json={})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _service_with(transport: RecordingTransport) -> OpenCriticService:
    service = OpenCriticService()
    service._client = httpx.AsyncClient(transport=transport, headers=service.headers)
    return service


@pytest.mark.asyncio
async def test_daily_quota_is_reported_without_retrying(no_sleep):
    transport = RecordingTransport([httpx.Response(
        429, json={"message": "You have exceeded the DAILY quota for Requests"},
        headers={"X-RateLimit-Requests-Reset": "1200"},
    )])
    async with _service_with(transport) as service:
        with pytest.raises(OpenCriticQuotaError, match="resets in 1200 seconds"):
            await service.get_game(7)
    assert len(transport.requests) == 1
    assert no_sleep == []


@pytest.mark.asyncio
async def test_client_is_created_once_and_reused():
    service = OpenCriticService()
    first = await service._get_client()
    second = await service._get_client()

    assert first is second
    await service.aclose()


@pytest.mark.asyncio
async def test_aclose_closes_and_allows_recreation():
    service = OpenCriticService()
    client = await service._get_client()
    await service.aclose()

    assert client.is_closed
    assert service._client is None

    recreated = await service._get_client()
    assert recreated is not client
    await service.aclose()


@pytest.mark.asyncio
async def test_many_requests_share_one_client():
    """The reconcile loop must not open a connection per game id."""
    transport = RecordingTransport([httpx.Response(200, json={"id": i}) for i in range(25)])
    service = _service_with(transport)
    before = await service._get_client()

    for game_id in range(25):
        await service.get_game(game_id, quiet_missing=True)

    assert len(transport.requests) == 25
    assert await service._get_client() is before
    await service.aclose()


@pytest.mark.asyncio
async def test_auth_header_still_sent_from_the_shared_client():
    """Headers moved from the per-request call onto the client itself."""
    transport = RecordingTransport([httpx.Response(200, json={"id": 1})])
    service = _service_with(transport)

    await service.get_game(1)

    sent = transport.requests[0]
    assert sent.headers["X-RapidAPI-Key"] == "test-key"
    assert "X-RapidAPI-Host" in sent.headers
    await service.aclose()


@pytest.mark.asyncio
async def test_network_errors_back_off_longer_than_before(no_sleep):
    """2s/3s could not ride out a DNS outage; the first two waits are now 5s/10s."""
    transport = RecordingTransport(
        [
            httpx.ConnectError("Temporary failure in name resolution"),
            httpx.ConnectError("Temporary failure in name resolution"),
            httpx.Response(200, json={"id": 7}),
        ]
    )
    service = _service_with(transport)

    result = await service.get_game(7)

    assert result == {"id": 7}
    assert no_sleep == [5, 10]
    await service.aclose()


@pytest.mark.asyncio
async def test_network_error_gives_up_after_max_retries(no_sleep):
    transport = RecordingTransport([httpx.ConnectError("boom")] * 3)
    service = _service_with(transport)

    assert await service.get_game(7) is None
    assert len(transport.requests) == 3
    await service.aclose()


@pytest.mark.asyncio
async def test_empty_network_error_still_names_the_exception(capsys, no_sleep):
    """`Request error, retrying in 3s: ` with nothing after the colon was a real log line."""
    transport = RecordingTransport([httpx.ConnectError(""), httpx.Response(200, json={})])
    service = _service_with(transport)

    await service.get_game(7)

    logged = capsys.readouterr().out
    assert "ConnectError" in logged
    await service.aclose()


@pytest.mark.asyncio
async def test_auth_failure_still_raises_rather_than_retrying(no_sleep):
    transport = RecordingTransport([httpx.Response(403, json={"message": "forbidden"})])
    service = _service_with(transport)

    with pytest.raises(opencritic_module.OpenCriticAuthError):
        await service.get_game(7)

    assert len(transport.requests) == 1
    await service.aclose()


@pytest.mark.asyncio
async def test_retryable_status_keeps_its_own_shorter_backoff(no_sleep):
    """HTTP 5xx is a server-side blip, not a dead network: unchanged 2s/3s."""
    transport = RecordingTransport(
        [httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"id": 9})]
    )
    service = _service_with(transport)

    assert await service.get_game(9) == {"id": 9}
    assert no_sleep == [2, 3]
    await service.aclose()


@pytest.mark.asyncio
async def test_quiet_404_returns_none_without_retrying(no_sleep):
    """Dead ids in the reconcile window must cost exactly one request."""
    transport = RecordingTransport([httpx.Response(404)])
    service = _service_with(transport)

    assert await service.get_game(99999, quiet_missing=True) is None
    assert len(transport.requests) == 1
    assert no_sleep == []
    await service.aclose()


def test_connect_timeout_is_shorter_than_read_timeout():
    """A runner that lost DNS should fail to the backoff fast, not sit on 30s x3."""
    assert opencritic_module.CONNECT_TIMEOUT_SECONDS < opencritic_module.READ_TIMEOUT_SECONDS


def test_network_backoff_helper_is_bounded():
    backoff = opencritic_module._network_retry_backoff
    assert backoff(0) == 5
    assert backoff(1) == 10
    # Never IndexErrors if max_retries is raised above the table length.
    assert backoff(99) == opencritic_module.NETWORK_RETRY_BACKOFF_SECONDS[-1]
