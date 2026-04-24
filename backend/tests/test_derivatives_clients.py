"""Unit tests for per-exchange derivatives fetchers.

Each test builds a mock HTTP transport that returns realistic exchange-shaped
JSON for the endpoints the fetcher hits, then asserts the parsed DerivSnap.
"""
import httpx
import pytest

from app.clients.derivatives import (
    fetch_binance,
    fetch_bybit,
    fetch_deribit,
    fetch_okx,
)


def _mock(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_binance_fetch():
    def handler(req: httpx.Request) -> httpx.Response:
        if "openInterest" in str(req.url):
            return httpx.Response(200, json={"symbol": "ETHUSDT", "openInterest": "500000.5"})
        if "premiumIndex" in str(req.url):
            return httpx.Response(
                200,
                json={
                    "symbol": "ETHUSDT",
                    "markPrice": "2300.50",
                    "lastFundingRate": "0.0001",
                },
            )
        return httpx.Response(404)

    async with _mock(handler) as http:
        snap = await fetch_binance(http)
    assert snap.exchange == "binance"
    assert snap.symbol == "ETHUSDT"
    assert snap.mark_price == 2300.50
    assert snap.funding_rate == 0.0001
    assert snap.oi_usd == pytest.approx(500000.5 * 2300.50)


@pytest.mark.asyncio
async def test_bybit_fetch():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": {
                    "list": [
                        {
                            "symbol": "ETHUSDT",
                            "markPrice": "2300",
                            "openInterest": "200000",
                            "fundingRate": "-0.0002",
                        }
                    ]
                }
            },
        )

    async with _mock(handler) as http:
        snap = await fetch_bybit(http)
    assert snap.exchange == "bybit"
    assert snap.mark_price == 2300.0
    assert snap.oi_usd == pytest.approx(200000 * 2300)
    assert snap.funding_rate == -0.0002


@pytest.mark.asyncio
async def test_okx_fetch():
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if "open-interest" in path:
            return httpx.Response(200, json={"data": [{"oiCcy": "350000", "instId": "ETH-USDT-SWAP"}]})
        if "funding-rate" in path:
            return httpx.Response(200, json={"data": [{"fundingRate": "0.00015"}]})
        if "/market/ticker" in path:
            return httpx.Response(200, json={"data": [{"last": "2310"}]})
        return httpx.Response(404)

    async with _mock(handler) as http:
        snap = await fetch_okx(http)
    assert snap.exchange == "okx"
    assert snap.symbol == "ETH-USDT-SWAP"
    assert snap.mark_price == 2310.0
    assert snap.funding_rate == 0.00015
    assert snap.oi_usd == pytest.approx(350000 * 2310)


@pytest.mark.asyncio
async def test_deribit_fetch():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": {
                    "instrument_name": "ETH-PERPETUAL",
                    "mark_price": 2299.5,
                    "open_interest": 450_000_000.0,
                    "funding_8h": 0.00008,
                }
            },
        )

    async with _mock(handler) as http:
        snap = await fetch_deribit(http)
    assert snap.exchange == "deribit"
    assert snap.symbol == "ETH-PERPETUAL"
    assert snap.oi_usd == 450_000_000.0
    assert snap.funding_rate == 0.00008
    assert snap.mark_price == 2299.5
