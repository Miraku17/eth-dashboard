"""Alert rule evaluators — pure-ish functions: (session, rule) -> list[fire].

Each evaluator returns a list of fire payloads. The worker layer handles
cooldown gating, persistence, and delivery.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from app.core.models import AlertEvent, AlertRule, PriceCandle, Transfer

DEFAULT_CANDLE_TF = "1m"


@dataclass(frozen=True)
class Fire:
    payload: dict
    dedup_key: str | None = None  # used to gate per-item (e.g., tx_hash:log_index)


def _latest_close(session: Session, symbol: str) -> tuple[float, datetime] | None:
    row = session.execute(
        select(PriceCandle)
        .where(PriceCandle.symbol == symbol, PriceCandle.timeframe == DEFAULT_CANDLE_TF)
        .order_by(PriceCandle.ts.desc())
        .limit(1)
    ).scalar_one_or_none()
    return (float(row.close), row.ts) if row else None


def _candle_at(
    session: Session, symbol: str, at_or_before: datetime
) -> tuple[float, datetime] | None:
    row = session.execute(
        select(PriceCandle)
        .where(
            PriceCandle.symbol == symbol,
            PriceCandle.timeframe == DEFAULT_CANDLE_TF,
            PriceCandle.ts <= at_or_before,
        )
        .order_by(PriceCandle.ts.desc())
        .limit(1)
    ).scalar_one_or_none()
    return (float(row.close), row.ts) if row else None


def _latest_event_ts(session: Session, rule_id: int) -> datetime | None:
    return session.execute(
        select(AlertEvent.fired_at)
        .where(AlertEvent.rule_id == rule_id)
        .order_by(desc(AlertEvent.fired_at))
        .limit(1)
    ).scalar_one_or_none()


def _existing_dedup_keys(session: Session, rule_id: int, since: datetime) -> set[str]:
    rows = session.execute(
        select(AlertEvent.payload)
        .where(AlertEvent.rule_id == rule_id, AlertEvent.fired_at >= since)
    ).scalars().all()
    keys: set[str] = set()
    for p in rows:
        k = (p or {}).get("_dedup")
        if k:
            keys.add(k)
    return keys


def evaluate_price_above(session: Session, rule: AlertRule) -> list[Fire]:
    p = rule.params
    threshold = float(p["threshold"])
    symbol = p.get("symbol", "ETHUSDT")
    row = _latest_close(session, symbol)
    if row is None:
        return []
    price, ts = row
    if price <= threshold:
        return []
    return [
        Fire(
            payload={
                "symbol": symbol,
                "price": price,
                "threshold": threshold,
                "direction": "above",
                "candle_ts": ts.isoformat(),
            }
        )
    ]


def evaluate_price_below(session: Session, rule: AlertRule) -> list[Fire]:
    p = rule.params
    threshold = float(p["threshold"])
    symbol = p.get("symbol", "ETHUSDT")
    row = _latest_close(session, symbol)
    if row is None:
        return []
    price, ts = row
    if price >= threshold:
        return []
    return [
        Fire(
            payload={
                "symbol": symbol,
                "price": price,
                "threshold": threshold,
                "direction": "below",
                "candle_ts": ts.isoformat(),
            }
        )
    ]


def evaluate_price_change_pct(session: Session, rule: AlertRule) -> list[Fire]:
    p = rule.params
    symbol = p.get("symbol", "ETHUSDT")
    window = int(p["window_min"])
    trigger_pct = float(p["pct"])

    latest = _latest_close(session, symbol)
    if latest is None:
        return []
    price_now, ts_now = latest

    past_at = ts_now - timedelta(minutes=window)
    past = _candle_at(session, symbol, past_at)
    if past is None:
        return []
    price_past, _ = past
    if price_past == 0:
        return []

    pct = (price_now - price_past) / price_past * 100.0
    triggered = (trigger_pct >= 0 and pct >= trigger_pct) or (
        trigger_pct < 0 and pct <= trigger_pct
    )
    if not triggered:
        return []
    return [
        Fire(
            payload={
                "symbol": symbol,
                "window_min": window,
                "pct_observed": pct,
                "pct_threshold": trigger_pct,
                "price_now": price_now,
                "price_past": price_past,
                "candle_ts": ts_now.isoformat(),
            }
        )
    ]


def evaluate_whale_transfer(session: Session, rule: AlertRule) -> list[Fire]:
    p = rule.params
    asset = p.get("asset", "ANY")
    min_usd = float(p["min_usd"])

    last_ts = _latest_event_ts(session, rule.id)
    cutoff = last_ts if last_ts else datetime.now(UTC) - timedelta(minutes=10)

    filters = [Transfer.ts > cutoff, Transfer.usd_value >= min_usd]
    if asset != "ANY":
        filters.append(Transfer.asset == asset)

    rows = session.execute(
        select(Transfer).where(and_(*filters)).order_by(Transfer.ts.asc()).limit(50)
    ).scalars().all()

    seen = _existing_dedup_keys(session, rule.id, cutoff - timedelta(minutes=30))
    fires: list[Fire] = []
    for t in rows:
        dedup = f"{t.tx_hash}:{t.log_index}"
        if dedup in seen:
            continue
        fires.append(
            Fire(
                payload={
                    "tx_hash": t.tx_hash,
                    "log_index": t.log_index,
                    "asset": t.asset,
                    "amount": float(t.amount),
                    "usd_value": float(t.usd_value) if t.usd_value is not None else None,
                    "from_addr": t.from_addr,
                    "to_addr": t.to_addr,
                    "ts": t.ts.isoformat(),
                    "_dedup": dedup,
                }
            )
        )
    return fires


EVALUATORS = {
    "price_above": evaluate_price_above,
    "price_below": evaluate_price_below,
    "price_change_pct": evaluate_price_change_pct,
    "whale_transfer": evaluate_whale_transfer,
}


def is_price_rule(rule_type: str) -> bool:
    """Price rules are cooldown-gated. Whale rules dedup per-transfer instead."""
    return rule_type.startswith("price_")
