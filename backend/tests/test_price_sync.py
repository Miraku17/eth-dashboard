from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.clients.binance import Kline
from app.core.models import PriceCandle
from app.services.price_sync import upsert_klines


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(PriceCandle).delete()
        s.commit()
        yield s


def _kline(ts_ms: int, close: float) -> Kline:
    return Kline(
        open_time_ms=ts_ms,
        open=close - 1,
        high=close + 2,
        low=close - 2,
        close=close,
        volume=10.0,
        close_time_ms=ts_ms + 3600_000 - 1,
    )


def test_upsert_inserts_new_candles(session):
    klines = [_kline(1714089600000, 3040.0), _kline(1714093200000, 3055.0)]

    upsert_klines(session, symbol="ETHUSDT", timeframe="1h", klines=klines)

    rows = session.execute(
        select(PriceCandle).order_by(PriceCandle.ts)
    ).scalars().all()
    assert len(rows) == 2
    assert float(rows[0].close) == 3040.0
    expected_ts = datetime.fromtimestamp(1714089600, tz=UTC)
    assert rows[0].ts == expected_ts
    assert rows[0].symbol == "ETHUSDT"
    assert rows[0].timeframe == "1h"


def test_upsert_updates_existing_candle(session):
    ts_ms = 1714089600000
    upsert_klines(session, "ETHUSDT", "1h", [_kline(ts_ms, 3000.0)])
    upsert_klines(session, "ETHUSDT", "1h", [_kline(ts_ms, 3100.0)])

    rows = session.execute(select(PriceCandle)).scalars().all()
    assert len(rows) == 1
    assert float(rows[0].close) == 3100.0


def test_upsert_empty_list_is_noop(session):
    upsert_klines(session, "ETHUSDT", "1h", [])
    assert session.query(PriceCandle).count() == 0


import httpx

from app.services.price_sync import backfill_timeframe, sync_latest


def _fixture_klines_for_range(start_ms: int, count: int, interval_ms: int) -> list:
    return [
        [
            start_ms + i * interval_ms,
            "3000.0", "3010.0", "2990.0", "3005.0", "10.0",
            start_ms + (i + 1) * interval_ms - 1,
            "30000.0", 1, "5.0", "15000.0", "0",
        ]
        for i in range(count)
    ]


@pytest.mark.asyncio
async def test_backfill_timeframe_fetches_and_upserts(session, migrated_engine):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json=_fixture_klines_for_range(1_700_000_000_000, 500, 3_600_000))
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.binance.com") as http:
        total = await backfill_timeframe(
            http, session, symbol="ETHUSDT", timeframe="1h",
            start_ms=1_700_000_000_000, end_ms=1_700_000_000_000 + 500 * 3_600_000,
        )

    assert total == 500
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_sync_latest_fetches_recent_candles(session, migrated_engine):
    def handler(request):
        assert "startTime" not in request.url.params
        return httpx.Response(200, json=_fixture_klines_for_range(1_700_000_000_000, 2, 3_600_000))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.binance.com") as http:
        n = await sync_latest(http, session, symbol="ETHUSDT", timeframe="1h")

    assert n == 2
