"""Alert rule evaluators — pure-ish functions: (session, rule) -> list[fire].

Each evaluator returns a list of fire payloads. The worker layer handles
cooldown gating, persistence, and delivery.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.core.models import AlertEvent, AlertRule, ExchangeFlow, PriceCandle, Transfer
from app.realtime.labels import label_for

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


def evaluate_whale_to_exchange(session: Session, rule: AlertRule) -> list[Fire]:
    """Whale transfer where at least one side is a labeled CEX address."""
    p = rule.params
    asset = p.get("asset", "ANY")
    min_usd = float(p["min_usd"])
    direction = p.get("direction", "any")

    last_ts = _latest_event_ts(session, rule.id)
    cutoff = last_ts if last_ts else datetime.now(UTC) - timedelta(minutes=10)

    filters = [Transfer.ts > cutoff, Transfer.usd_value >= min_usd]
    if asset != "ANY":
        filters.append(Transfer.asset == asset)

    rows = session.execute(
        select(Transfer).where(and_(*filters)).order_by(Transfer.ts.asc()).limit(100)
    ).scalars().all()

    seen = _existing_dedup_keys(session, rule.id, cutoff - timedelta(minutes=30))
    fires: list[Fire] = []
    for t in rows:
        from_lbl = label_for(t.from_addr)
        to_lbl = label_for(t.to_addr)

        if direction == "to":
            matched_label = to_lbl if to_lbl else None
        elif direction == "from":
            matched_label = from_lbl if from_lbl else None
        else:  # any
            matched_label = to_lbl or from_lbl

        if not matched_label:
            continue

        dedup = f"{t.tx_hash}:{t.log_index}"
        if dedup in seen:
            continue
        # Describe which side matched, for clearer notifications.
        if to_lbl and from_lbl:
            match_side = "both"
        elif to_lbl:
            match_side = "to"
        else:
            match_side = "from"
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
                    "from_label": from_lbl,
                    "to_label": to_lbl,
                    "match_side": match_side,
                    "ts": t.ts.isoformat(),
                    "_dedup": dedup,
                }
            )
        )
    return fires


def evaluate_exchange_netflow(session: Session, rule: AlertRule) -> list[Fire]:
    """Sum ExchangeFlow rows in the window and fire if the net (or one side) exceeds threshold."""
    p = rule.params
    exchange = p.get("exchange", "ANY")
    window_h = int(p["window_h"])
    threshold = float(p["threshold_usd"])
    direction = p.get("direction", "net")

    cutoff = datetime.now(UTC) - timedelta(hours=window_h)

    def _sum(side: str) -> float:
        filters = [ExchangeFlow.ts_bucket >= cutoff, ExchangeFlow.direction == side]
        if exchange != "ANY":
            filters.append(ExchangeFlow.exchange == exchange)
        total = session.execute(
            select(func.coalesce(func.sum(ExchangeFlow.usd_value), 0)).where(and_(*filters))
        ).scalar_one()
        return float(total or 0)

    inflow = _sum("in")
    outflow = _sum("out")
    net = inflow - outflow

    if direction == "in":
        value = inflow
        triggered = inflow >= threshold
    elif direction == "out":
        value = outflow
        triggered = outflow >= threshold
    else:  # net — trigger when |net| >= threshold
        value = net
        triggered = abs(net) >= threshold

    if not triggered:
        return []
    return [
        Fire(
            payload={
                "exchange": exchange,
                "window_h": window_h,
                "direction": direction,
                "inflow_usd": inflow,
                "outflow_usd": outflow,
                "net_usd": net,
                "value_usd": value,
                "threshold_usd": threshold,
            }
        )
    ]


EVALUATORS = {
    "price_above": evaluate_price_above,
    "price_below": evaluate_price_below,
    "price_change_pct": evaluate_price_change_pct,
    "whale_transfer": evaluate_whale_transfer,
    "whale_to_exchange": evaluate_whale_to_exchange,
    "exchange_netflow": evaluate_exchange_netflow,
}


def is_cooldown_gated(rule_type: str) -> bool:
    """Cooldown applies to aggregate rules (price + exchange_netflow).
    Per-transfer rules (whale_*) dedup on tx_hash instead."""
    return rule_type.startswith("price_") or rule_type == "exchange_netflow"


# Back-compat shim; older callers used `is_price_rule`. Keep it working.
def is_price_rule(rule_type: str) -> bool:
    return is_cooldown_gated(rule_type)
