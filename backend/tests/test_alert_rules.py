from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import (
    AlertEvent,
    AlertRule,
    ExchangeFlow,
    PriceCandle,
    Transfer,
    WalletScore,
)
from app.services.alerts.rules import (
    evaluate_exchange_netflow,
    evaluate_price_above,
    evaluate_price_below,
    evaluate_price_change_pct,
    evaluate_wallet_score_move,
    evaluate_whale_to_exchange,
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
        s.query(ExchangeFlow).delete()
        s.query(WalletScore).delete()
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


BINANCE_14 = "0x28c6c06298d514db089934071355e5743bf21d60"  # from labels module


def test_whale_to_exchange_fires_when_to_is_labeled(session):
    rule = AlertRule(
        name="w2e", rule_type="whale_to_exchange",
        params={"asset": "ANY", "min_usd": 1_000_000.0, "direction": "any"},
        channels=[],
    )
    session.add(rule)
    session.commit()

    now = datetime.now(UTC)
    session.add(Transfer(
        tx_hash="0xin", log_index=0, block_number=1,
        ts=now - timedelta(minutes=2),
        from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        to_addr=BINANCE_14,
        asset="USDT", amount=Decimal("5000000"), usd_value=Decimal("5000000"),
    ))
    session.add(Transfer(
        tx_hash="0xplain", log_index=0, block_number=2,
        ts=now - timedelta(minutes=1),
        from_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        to_addr="0xcccccccccccccccccccccccccccccccccccccccc",
        asset="USDT", amount=Decimal("5000000"), usd_value=Decimal("5000000"),
    ))
    session.commit()

    fires = evaluate_whale_to_exchange(session, rule)
    assert {f.payload["tx_hash"] for f in fires} == {"0xin"}
    assert fires[0].payload["to_label"] == "Binance 14"
    assert fires[0].payload["match_side"] == "to"


def test_whale_to_exchange_direction_from_only(session):
    rule = AlertRule(
        name="w2e", rule_type="whale_to_exchange",
        params={"asset": "ANY", "min_usd": 1_000_000.0, "direction": "from"},
        channels=[],
    )
    session.add(rule)
    session.commit()

    now = datetime.now(UTC)
    # to is labeled — should NOT fire when direction=from
    session.add(Transfer(
        tx_hash="0xto", log_index=0, block_number=1,
        ts=now - timedelta(minutes=2),
        from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        to_addr=BINANCE_14,
        asset="USDT", amount=Decimal("5000000"), usd_value=Decimal("5000000"),
    ))
    # from is labeled — SHOULD fire
    session.add(Transfer(
        tx_hash="0xfrom", log_index=0, block_number=2,
        ts=now - timedelta(minutes=1),
        from_addr=BINANCE_14,
        to_addr="0xcccccccccccccccccccccccccccccccccccccccc",
        asset="USDT", amount=Decimal("5000000"), usd_value=Decimal("5000000"),
    ))
    session.commit()

    fires = evaluate_whale_to_exchange(session, rule)
    assert {f.payload["tx_hash"] for f in fires} == {"0xfrom"}


def test_exchange_netflow_fires_when_inflow_exceeds_threshold(session):
    rule = AlertRule(
        name="flow", rule_type="exchange_netflow",
        params={
            "exchange": "Binance",
            "window_h": 24,
            "threshold_usd": 100_000_000.0,
            "direction": "in",
        },
        channels=[],
    )
    session.add(rule)
    session.commit()

    now = datetime.now(UTC).replace(microsecond=0)
    for i in range(3):
        session.add(ExchangeFlow(
            exchange="Binance", direction="in", asset="ETH",
            ts_bucket=now - timedelta(hours=2, minutes=i),
            usd_value=Decimal("50000000"),
        ))
    session.add(ExchangeFlow(
        exchange="Binance", direction="out", asset="ETH",
        ts_bucket=now - timedelta(hours=1),
        usd_value=Decimal("10000000"),
    ))
    session.commit()

    fires = evaluate_exchange_netflow(session, rule)
    # 3 × $50M inflow = $150M >= $100M threshold (direction=in)
    assert len(fires) == 1
    assert fires[0].payload["inflow_usd"] == 150_000_000.0


def test_exchange_netflow_net_mode(session):
    rule = AlertRule(
        name="flow", rule_type="exchange_netflow",
        params={
            "exchange": "ANY",
            "window_h": 24,
            "threshold_usd": 50_000_000.0,
            "direction": "net",
        },
        channels=[],
    )
    session.add(rule)
    session.commit()

    now = datetime.now(UTC).replace(microsecond=0)
    session.add(ExchangeFlow(
        exchange="Binance", direction="in", asset="ETH",
        ts_bucket=now - timedelta(hours=3),
        usd_value=Decimal("80000000"),
    ))
    session.add(ExchangeFlow(
        exchange="Binance", direction="out", asset="ETH",
        ts_bucket=now - timedelta(hours=2),
        usd_value=Decimal("20000000"),
    ))
    session.commit()

    fires = evaluate_exchange_netflow(session, rule)
    # net = 80 - 20 = 60M, |net| > 50M threshold → fires
    assert len(fires) == 1
    assert fires[0].payload["net_usd"] == 60_000_000.0


def test_exchange_netflow_below_threshold_no_fire(session):
    rule = AlertRule(
        name="flow", rule_type="exchange_netflow",
        params={
            "exchange": "ANY",
            "window_h": 24,
            "threshold_usd": 100_000_000.0,
            "direction": "net",
        },
        channels=[],
    )
    session.add(rule)
    session.commit()

    now = datetime.now(UTC).replace(microsecond=0)
    session.add(ExchangeFlow(
        exchange="Binance", direction="in", asset="ETH",
        ts_bucket=now - timedelta(hours=1),
        usd_value=Decimal("10000000"),
    ))
    session.commit()

    assert evaluate_exchange_netflow(session, rule) == []


# ---------- wallet_score_move ----------

# Lowercased addresses match how the daily scoring cron writes wallet_score.
SMART_FROM_ADDR = "0x1111111111111111111111111111111111111111"
SMART_TO_ADDR = "0x2222222222222222222222222222222222222222"
NOISE_ADDR = "0x3333333333333333333333333333333333333333"


def _smart_score(wallet: str, score: float) -> WalletScore:
    return WalletScore(
        wallet=wallet,
        trades_30d=20,
        volume_usd_30d=Decimal("1000000"),
        realized_pnl_30d=Decimal(str(score)),
        win_rate_30d=0.55,
        score=score,
        updated_at=datetime.now(UTC),
    )


def test_wallet_score_move_fires_when_smart_party_moves(session):
    rule = AlertRule(
        name="sm", rule_type="wallet_score_move",
        params={
            "asset": "ANY",
            "min_usd": 1_000_000.0,
            "min_score": 100_000.0,
            "direction": "any",
        },
        channels=[],
    )
    session.add(rule)
    session.add(_smart_score(SMART_FROM_ADDR, 250_000.0))
    session.commit()

    now = datetime.now(UTC)
    # whale-grade move from a smart wallet — should fire
    session.add(Transfer(
        tx_hash="0xsmart", log_index=0, block_number=1,
        ts=now - timedelta(minutes=2),
        from_addr=SMART_FROM_ADDR, to_addr=NOISE_ADDR,
        asset="USDT", amount=Decimal("2000000"), usd_value=Decimal("2000000"),
    ))
    # whale-grade but neither side scored — should NOT fire
    session.add(Transfer(
        tx_hash="0xnoise", log_index=0, block_number=2,
        ts=now - timedelta(minutes=1),
        from_addr=NOISE_ADDR, to_addr="0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        asset="USDT", amount=Decimal("3000000"), usd_value=Decimal("3000000"),
    ))
    session.commit()

    fires = evaluate_wallet_score_move(session, rule)
    assert {f.payload["tx_hash"] for f in fires} == {"0xsmart"}
    assert fires[0].payload["match_side"] == "from"
    assert fires[0].payload["from_score"] == 250_000.0


def test_wallet_score_move_below_floor_excluded(session):
    """A scored wallet below `min_score` must not match — the floor is the
    whole point of the rule."""
    rule = AlertRule(
        name="sm", rule_type="wallet_score_move",
        params={
            "asset": "ANY",
            "min_usd": 1_000_000.0,
            "min_score": 100_000.0,
            "direction": "any",
        },
        channels=[],
    )
    session.add(rule)
    session.add(_smart_score(SMART_FROM_ADDR, 5_000.0))  # below the $100k floor
    session.commit()

    session.add(Transfer(
        tx_hash="0xlow", log_index=0, block_number=1,
        ts=datetime.now(UTC) - timedelta(minutes=2),
        from_addr=SMART_FROM_ADDR, to_addr=NOISE_ADDR,
        asset="USDT", amount=Decimal("2000000"), usd_value=Decimal("2000000"),
    ))
    session.commit()

    assert evaluate_wallet_score_move(session, rule) == []


def test_wallet_score_move_direction_to_requires_smart_receiver(session):
    """direction='to' restricts to transfers where the *receiver* is smart;
    a transfer from a smart wallet to a noise wallet must not match."""
    rule = AlertRule(
        name="sm", rule_type="wallet_score_move",
        params={
            "asset": "ANY",
            "min_usd": 1_000_000.0,
            "min_score": 100_000.0,
            "direction": "to",
        },
        channels=[],
    )
    session.add(rule)
    session.add(_smart_score(SMART_FROM_ADDR, 250_000.0))
    session.add(_smart_score(SMART_TO_ADDR, 500_000.0))
    session.commit()

    now = datetime.now(UTC)
    # smart → noise: under direction=to this should NOT fire
    session.add(Transfer(
        tx_hash="0xsmartfrom", log_index=0, block_number=1,
        ts=now - timedelta(minutes=2),
        from_addr=SMART_FROM_ADDR, to_addr=NOISE_ADDR,
        asset="USDT", amount=Decimal("2000000"), usd_value=Decimal("2000000"),
    ))
    # noise → smart: should fire
    session.add(Transfer(
        tx_hash="0xsmartto", log_index=0, block_number=2,
        ts=now - timedelta(minutes=1),
        from_addr=NOISE_ADDR, to_addr=SMART_TO_ADDR,
        asset="USDT", amount=Decimal("2000000"), usd_value=Decimal("2000000"),
    ))
    session.commit()

    fires = evaluate_wallet_score_move(session, rule)
    assert {f.payload["tx_hash"] for f in fires} == {"0xsmartto"}
    assert fires[0].payload["match_side"] == "to"
    assert fires[0].payload["to_score"] == 500_000.0
