from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import AlertEvent, AlertRule, PriceCandle, Transfer
from app.services.alerts.rules import (
    evaluate_price_above,
    evaluate_price_below,
    evaluate_price_change_pct,
    evaluate_whale_transfer,
)


def _candle(ts: datetime, price: float) -> PriceCandle:
    return PriceCandle(
        symbol="ETHUSDT",
        timeframe="1m",
        ts=ts,
        open=Decimal(str(price)),
        high=Decimal(str(price)),
        low=Decimal(str(price)),
        close=Decimal(str(price)),
        volume=Decimal("1"),
    )


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(AlertEvent).delete()
        s.query(AlertRule).delete()
        s.query(PriceCandle).delete()
        s.query(Transfer).delete()
        s.commit()
        yield s


def test_price_above_fires(session):
    now = datetime.now(UTC).replace(microsecond=0)
    session.add(_candle(now, 4200.0))
    session.commit()
    rule = AlertRule(
        id=0,
        name="r1",
        rule_type="price_above",
        params={"symbol": "ETHUSDT", "threshold": 4000.0},
        channels=[],
    )
    fires = evaluate_price_above(session, rule)
    assert len(fires) == 1
    assert fires[0].payload["price"] == 4200.0
    assert fires[0].payload["direction"] == "above"


def test_price_above_does_not_fire(session):
    session.add(_candle(datetime.now(UTC), 3999.0))
    session.commit()
    rule = AlertRule(
        id=0, name="r", rule_type="price_above",
        params={"symbol": "ETHUSDT", "threshold": 4000.0}, channels=[],
    )
    assert evaluate_price_above(session, rule) == []


def test_price_below_fires(session):
    session.add(_candle(datetime.now(UTC), 3100.0))
    session.commit()
    rule = AlertRule(
        id=0, name="r", rule_type="price_below",
        params={"symbol": "ETHUSDT", "threshold": 3200.0}, channels=[],
    )
    fires = evaluate_price_below(session, rule)
    assert len(fires) == 1
    assert fires[0].payload["direction"] == "below"


def test_price_change_pct_up(session):
    t0 = datetime.now(UTC).replace(microsecond=0, second=0)
    session.add(_candle(t0 - timedelta(minutes=60), 3000.0))
    session.add(_candle(t0, 3150.0))  # +5%
    session.commit()
    rule = AlertRule(
        id=0, name="r", rule_type="price_change_pct",
        params={"symbol": "ETHUSDT", "window_min": 60, "pct": 3.0}, channels=[],
    )
    fires = evaluate_price_change_pct(session, rule)
    assert len(fires) == 1
    assert fires[0].payload["pct_observed"] == pytest.approx(5.0)


def test_price_change_pct_down_trigger(session):
    t0 = datetime.now(UTC).replace(microsecond=0, second=0)
    session.add(_candle(t0 - timedelta(minutes=30), 3000.0))
    session.add(_candle(t0, 2850.0))  # -5%
    session.commit()
    rule = AlertRule(
        id=0, name="r", rule_type="price_change_pct",
        params={"symbol": "ETHUSDT", "window_min": 30, "pct": -3.0}, channels=[],
    )
    fires = evaluate_price_change_pct(session, rule)
    assert len(fires) == 1
    assert fires[0].payload["pct_observed"] == pytest.approx(-5.0)


def test_price_change_pct_below_threshold_no_fire(session):
    t0 = datetime.now(UTC).replace(microsecond=0, second=0)
    session.add(_candle(t0 - timedelta(minutes=30), 3000.0))
    session.add(_candle(t0, 3030.0))  # +1%
    session.commit()
    rule = AlertRule(
        id=0, name="r", rule_type="price_change_pct",
        params={"symbol": "ETHUSDT", "window_min": 30, "pct": 3.0}, channels=[],
    )
    assert evaluate_price_change_pct(session, rule) == []


def test_whale_transfer_fires_for_new_only(session):
    # seed a rule so it has a real id
    rule = AlertRule(
        name="w", rule_type="whale_transfer",
        params={"asset": "ETH", "min_usd": 1_000_000.0}, channels=[],
    )
    session.add(rule)
    session.commit()

    now = datetime.now(UTC)
    # First-run cutoff is now-10m, so older transfers are intentionally skipped.
    session.add(Transfer(
        tx_hash="0xancient", log_index=0, block_number=0,
        ts=now - timedelta(minutes=30),
        from_addr="0xa", to_addr="0xb",
        asset="ETH", amount=Decimal("1000"), usd_value=Decimal("3000000"),
    ))
    session.add(Transfer(
        tx_hash="0xrecent", log_index=0, block_number=2,
        ts=now - timedelta(minutes=5),
        from_addr="0xc", to_addr="0xd",
        asset="ETH", amount=Decimal("800"), usd_value=Decimal("2400000"),
    ))
    session.add(Transfer(
        tx_hash="0xnewest", log_index=0, block_number=3,
        ts=now - timedelta(minutes=1),
        from_addr="0xc", to_addr="0xd",
        asset="ETH", amount=Decimal("500"), usd_value=Decimal("1500000"),
    ))
    session.add(Transfer(
        tx_hash="0xsmall", log_index=0, block_number=4,
        ts=now - timedelta(minutes=1),
        from_addr="0xe", to_addr="0xf",
        asset="ETH", amount=Decimal("10"), usd_value=Decimal("30000"),
    ))
    session.commit()

    fires = evaluate_whale_transfer(session, rule)
    # First-run cutoff = now-10m: ancient is too old, small is below threshold.
    assert {f.payload["tx_hash"] for f in fires} == {"0xrecent", "0xnewest"}


def test_whale_transfer_respects_last_event_cutoff(session):
    rule = AlertRule(
        name="w", rule_type="whale_transfer",
        params={"asset": "ANY", "min_usd": 1_000_000.0}, channels=[],
    )
    session.add(rule)
    session.commit()

    now = datetime.now(UTC)
    past_event_time = now - timedelta(minutes=5)
    session.add(AlertEvent(
        rule_id=rule.id, fired_at=past_event_time,
        payload={"_dedup": "0xold:0"}, delivered={},
    ))
    session.add(Transfer(
        tx_hash="0xold", log_index=0, block_number=1,
        ts=past_event_time - timedelta(minutes=1),  # before last event
        from_addr="0xa", to_addr="0xb", asset="USDT",
        amount=Decimal("2000000"), usd_value=Decimal("2000000"),
    ))
    session.add(Transfer(
        tx_hash="0xfresh", log_index=0, block_number=2,
        ts=now - timedelta(minutes=1),  # after last event
        from_addr="0xc", to_addr="0xd", asset="USDT",
        amount=Decimal("1500000"), usd_value=Decimal("1500000"),
    ))
    session.commit()

    fires = evaluate_whale_transfer(session, rule)
    assert {f.payload["tx_hash"] for f in fires} == {"0xfresh"}
