import hashlib
import hmac
import json
import os

import httpx
import pytest

from app.services.alerts.delivery import (
    dispatch,
    format_telegram_message,
    send_webhook,
)


@pytest.fixture(autouse=True)
def _minimal_env(monkeypatch):
    """Delivery tests don't need a DB, but `get_settings()` still instantiates
    Pydantic settings — provide the minimum required fields."""
    monkeypatch.setenv("POSTGRES_USER", "x")
    monkeypatch.setenv("POSTGRES_PASSWORD", "x")
    monkeypatch.setenv("POSTGRES_DB", "x")
    monkeypatch.setenv("POSTGRES_HOST", "x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    # Clear anything that might be inherited from .env.
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "WEBHOOK_SIGNING_SECRET"):
        os.environ.pop(k, None)


def test_format_price_message():
    msg = format_telegram_message(
        "ETH above 4k",
        "price_above",
        {"symbol": "ETHUSDT", "price": 4200.0, "threshold": 4000.0},
    )
    assert "ETH above 4k" in msg
    assert "ETHUSDT" in msg
    assert "4.2K" in msg  # $4200 formatted compact


def test_format_whale_message():
    msg = format_telegram_message(
        "Whale ETH",
        "whale_transfer",
        {
            "asset": "ETH",
            "amount": 1200.0,
            "usd_value": 3600000,
            "from_addr": "0xaaa",
            "to_addr": "0xbbb",
            "tx_hash": "0xdead",
        },
    )
    assert "🐋" in msg
    assert "etherscan.io/tx/0xdead" in msg


async def test_send_webhook_signs_body(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        seen["sig"] = request.headers.get("X-Etherscope-Signature")
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        res = await send_webhook(
            http, "https://example.com/hook", {"hello": "world"}, secret="topsecret"
        )
    assert res == {"ok": True, "status": 200}
    expected = hmac.new(
        b"topsecret",
        json.dumps({"hello": "world"}, separators=(",", ":"), sort_keys=True).encode(),
        hashlib.sha256,
    ).hexdigest()
    assert seen["sig"] == f"sha256={expected}"


async def test_dispatch_unknown_channel_is_recorded():
    async with httpx.AsyncClient() as http:
        res = await dispatch(http, [{"type": "banana"}], "r", "price_above", {})
    assert res["banana:0"]["ok"] is False
    assert "unknown" in res["banana:0"]["error"]


async def test_dispatch_missing_webhook_url():
    async with httpx.AsyncClient() as http:
        res = await dispatch(http, [{"type": "webhook"}], "r", "price_above", {})
    assert res["webhook:0"]["ok"] is False


@pytest.mark.asyncio
async def test_dispatch_telegram_not_configured(monkeypatch):
    # Settings default token/chat id are empty strings → should report error
    async with httpx.AsyncClient() as http:
        res = await dispatch(http, [{"type": "telegram"}], "r", "price_above", {})
    assert res["telegram:0"]["ok"] is False
    assert "not configured" in res["telegram:0"]["error"]
