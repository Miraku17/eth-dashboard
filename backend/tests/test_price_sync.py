from datetime import datetime, timedelta, timezone
from decimal import Decimal

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
    expected_ts = datetime.fromtimestamp(1714089600, tz=timezone.utc)
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
