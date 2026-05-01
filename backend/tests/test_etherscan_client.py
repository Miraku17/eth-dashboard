import json
import httpx
import pytest

from app.clients.etherscan import (
    EtherscanClient,
    EtherscanRateLimited,
    EtherscanUnavailable,
)


def _ok(rows):
    return httpx.Response(200, json={"status": "1", "message": "OK", "result": rows})


def _empty():
    return httpx.Response(200, json={"status": "0", "message": "No transactions found", "result": []})


async def test_txlist_asc_returns_rows():
    rows = [{"hash": "0xabc", "from": "0xfrom", "to": "0xto", "value": "1000000000000000000",
             "blockNumber": "100", "timeStamp": "1714000000"}]

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v2/api"
        params = dict(req.url.params)
        assert params["module"] == "account"
        assert params["action"] == "txlist"
        assert params["address"] == "0xtarget"
        assert params["sort"] == "asc"
        assert params["page"] == "1"
        assert params["chainid"] == "1"
        return _ok(rows)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        out = await client.txlist("0xtarget", sort="asc", page=1, offset=10)
    assert out == rows


async def test_empty_result_treated_as_empty_list():
    transport = httpx.MockTransport(lambda r: _empty())
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        out = await client.txlist("0xtarget")
    assert out == []


async def test_rate_limit_message_raises_typed_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": "0",
            "message": "NOTOK",
            "result": "Max rate limit reached",
        })
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        with pytest.raises(EtherscanRateLimited):
            await client.txlist("0xtarget", _max_attempts=1)


async def test_5xx_retries_then_raises():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="bad gateway")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        with pytest.raises(EtherscanUnavailable):
            await client.txlist("0xtarget", _max_attempts=3, _backoff_s=0.0)
    assert calls["n"] == 3


async def test_5xx_retry_then_recover():
    seq = [
        httpx.Response(502, text="bad"),
        _ok([{"hash": "0x1"}]),
    ]
    it = iter(seq)

    def handler(req: httpx.Request) -> httpx.Response:
        return next(it)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        out = await client.txlist("0xtarget", _max_attempts=3, _backoff_s=0.0)
    assert out == [{"hash": "0x1"}]


async def test_tokentx_passes_contract_filter():
    rows = [{"hash": "0xabc", "contractAddress": "0xusdc"}]
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(dict(req.url.params))
        return _ok(rows)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        await client.tokentx("0xtarget", contract_address="0xusdc")
    assert seen["action"] == "tokentx"
    assert seen["contractaddress"] == "0xusdc"
