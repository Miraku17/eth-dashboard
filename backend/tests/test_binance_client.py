import json
from pathlib import Path

import httpx
import pytest

from app.clients.binance import BinanceClient, Kline

FIXTURE = Path(__file__).parent / "fixtures" / "binance_klines_1h.json"


@pytest.mark.asyncio
async def test_fetch_klines_parses_binance_response():
    fixture = json.loads(FIXTURE.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/klines"
        assert request.url.params["symbol"] == "ETHUSDT"
        assert request.url.params["interval"] == "1h"
        assert request.url.params["limit"] == "500"
        return httpx.Response(200, json=fixture)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.binance.com") as http:
        client = BinanceClient(http)
        klines = await client.fetch_klines("ETHUSDT", "1h", limit=500)

    assert len(klines) == 3
    assert isinstance(klines[0], Kline)
    assert klines[0].open_time_ms == 1714089600000
    assert klines[0].open == 3000.0
    assert klines[0].close == 3040.0
    assert klines[0].volume == 120.5


@pytest.mark.asyncio
async def test_fetch_klines_supports_time_range():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["startTime"] == "1714000000000"
        assert request.url.params["endTime"] == "1714100000000"
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.binance.com") as http:
        client = BinanceClient(http)
        result = await client.fetch_klines(
            "ETHUSDT", "1h", start_ms=1714000000000, end_ms=1714100000000
        )

    assert result == []
