"""Unit tests for the thin Lighthouse beacon-API client."""
import httpx
import pytest

from app.clients.beacon import BeaconClient, GWEI_PER_ETH


@pytest.mark.asyncio
async def test_active_validator_count_parses_data_length():
    """Returns len(response['data']) when the call succeeds."""
    fake_data = {"data": [{"index": str(i), "balance": "32000000000"} for i in range(5)]}
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
        return httpx.Response(200, json={"data": [{"balance": "32000000000"} for _ in range(3)]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://beacon.test") as http:
        client = BeaconClient(http, cache_ttl_s=300)
        assert await client.active_validator_count() == 3
        assert await client.active_validator_count() == 3
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_active_validator_summary_sums_balances():
    """total_balance_gwei = sum of every validator's balance field."""
    fake = {
        "data": [
            {"index": "0", "balance": "32000000000"},      # 32 ETH
            {"index": "1", "balance": "32500000000"},      # 32.5 ETH (validator with rewards)
            {"index": "2", "balance": "31500000000"},      # 31.5 ETH (slashed-ish)
        ]
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=fake))
    async with httpx.AsyncClient(transport=transport, base_url="http://beacon.test") as http:
        client = BeaconClient(http)
        s = await client.active_validator_summary()
    assert s is not None
    assert s.count == 3
    assert s.total_balance_gwei == 96_000_000_000
    assert s.total_eth == pytest.approx(96.0)
    assert GWEI_PER_ETH == 10**9


@pytest.mark.asyncio
async def test_active_validator_summary_skips_malformed_balances():
    """A validator entry without a balance field (or non-numeric) is counted but contributes 0 gwei."""
    fake = {
        "data": [
            {"index": "0", "balance": "32000000000"},  # 32 ETH
            {"index": "1"},                             # missing balance — skip
            {"index": "2", "balance": "garbage"},       # non-numeric — skip
            {"index": "3", "balance": "16000000000"},   # 16 ETH
        ]
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=fake))
    async with httpx.AsyncClient(transport=transport, base_url="http://beacon.test") as http:
        client = BeaconClient(http)
        s = await client.active_validator_summary()
    assert s is not None
    assert s.count == 4
    assert s.total_eth == pytest.approx(48.0)
