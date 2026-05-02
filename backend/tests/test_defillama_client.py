"""Unit tests for the DefiLlama public-API client. Mock httpx via MockTransport."""
import httpx
import pytest

from app.clients.defillama import DefiLlamaClient


def _fake_protocol_response(token_breakdown: dict[str, float] | None) -> dict:
    """Build a minimal /protocol/{slug} response shape DefiLlama returns."""
    chain_tvls = {}
    if token_breakdown is not None:
        chain_tvls["Ethereum"] = {
            "tokensInUsd": [
                # earlier daily snapshot (ignored)
                {"date": 1714540800, "tokens": {k: v * 0.9 for k, v in token_breakdown.items()}},
                # latest snapshot (consumed)
                {"date": 1714627200, "tokens": token_breakdown},
            ]
        }
    return {"name": "Test Protocol", "chainTvls": chain_tvls}


@pytest.mark.asyncio
async def test_fetch_protocol_tvl_parses_latest_eth_snapshot():
    fake = _fake_protocol_response({"USDC": 4_320_000_000.0, "USDT": 3_100_000_000.0})
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=fake))
    async with httpx.AsyncClient(transport=transport, base_url="http://llama.test") as http:
        client = DefiLlamaClient(http)
        out = await client.fetch_protocol_tvl("aave-v3")
    assert out == {"USDC": 4_320_000_000.0, "USDT": 3_100_000_000.0}


@pytest.mark.asyncio
async def test_fetch_protocol_tvl_returns_empty_on_http_error():
    def boom(req):
        raise httpx.ConnectError("refused")
    transport = httpx.MockTransport(boom)
    async with httpx.AsyncClient(transport=transport, base_url="http://llama.test") as http:
        client = DefiLlamaClient(http)
        out = await client.fetch_protocol_tvl("aave-v3")
    assert out == {}


@pytest.mark.asyncio
async def test_fetch_protocol_tvl_returns_empty_when_no_ethereum_chain():
    fake = _fake_protocol_response(None)  # no Ethereum entry
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=fake))
    async with httpx.AsyncClient(transport=transport, base_url="http://llama.test") as http:
        client = DefiLlamaClient(http)
        out = await client.fetch_protocol_tvl("aave-v3")
    assert out == {}
