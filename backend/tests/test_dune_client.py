import json
from pathlib import Path

import httpx
import pytest

from app.clients.dune import DuneClient, DuneExecutionError

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_execute_and_fetch_returns_rows():
    exec_response = json.loads((FIX / "dune_execution_response.json").read_text())
    results_response = json.loads((FIX / "dune_results_exchange_flows.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/execute"):
            return httpx.Response(200, json=exec_response)
        if request.method == "GET" and request.url.path.endswith("/status"):
            return httpx.Response(200, json={"state": "QUERY_STATE_COMPLETED"})
        if request.method == "GET" and "/results" in request.url.path:
            return httpx.Response(200, json=results_response)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.dune.com") as http:
        client = DuneClient(http, api_key="test-key")
        rows = await client.execute_and_fetch(query_id=12345, poll_interval_s=0)

    assert len(rows) == 3
    assert rows[0]["exchange"] == "Binance"
    assert rows[2]["asset"] == "USDC"


@pytest.mark.asyncio
async def test_execute_sends_api_key_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-dune-api-key") == "test-key"
        return httpx.Response(200, json={"execution_id": "x", "state": "QUERY_STATE_PENDING"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.dune.com") as http:
        client = DuneClient(http, api_key="test-key")
        eid = await client.execute(12345)

    assert eid == "x"


@pytest.mark.asyncio
async def test_execute_and_fetch_raises_on_failure():
    def handler(request):
        if request.url.path.endswith("/execute"):
            return httpx.Response(200, json={"execution_id": "x", "state": "QUERY_STATE_PENDING"})
        return httpx.Response(200, json={"state": "QUERY_STATE_FAILED"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.dune.com") as http:
        client = DuneClient(http, api_key="test-key")
        with pytest.raises(DuneExecutionError):
            await client.execute_and_fetch(12345, poll_interval_s=0)
