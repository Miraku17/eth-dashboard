"""Unit tests for the thin Lighthouse beacon-API client."""
import httpx
import pytest

from app.clients.beacon import BeaconClient


@pytest.mark.asyncio
async def test_active_validator_count_parses_data_length():
    """Returns len(response['data']) when the call succeeds."""
    fake_data = {"data": [{"index": str(i)} for i in range(5)]}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=fake_data))
    async with httpx.AsyncClient(transport=transport, base_url="http://beacon.test") as http:
        client = BeaconClient(http)
        n = await client.active_validator_count()
    assert n == 5


@pytest.mark.asyncio
async def test_active_validator_count_returns_none_on_http_error():
    """Network failure → None (caller hides the tile)."""
    def boom(req):
        raise httpx.ConnectError("refused")
    transport = httpx.MockTransport(boom)
    async with httpx.AsyncClient(transport=transport, base_url="http://beacon.test") as http:
        client = BeaconClient(http)
        n = await client.active_validator_count()
    assert n is None


@pytest.mark.asyncio
async def test_active_validator_count_uses_cache():
    """Second call within TTL returns cached value without re-hitting the network."""
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json={"data": [{}, {}, {}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://beacon.test") as http:
        client = BeaconClient(http, cache_ttl_s=300)
        assert await client.active_validator_count() == 3
        assert await client.active_validator_count() == 3
    assert calls["n"] == 1
