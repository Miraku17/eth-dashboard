"""Build payload + ship Telegram alert for a watchlist perp event.

Sits between the arbitrum_listener decoder and the existing
alerts.delivery layer so we get retries + formatting for free.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from app.core.db import get_sessionmaker
from app.core.models import AlertEvent, AlertRule, PerpWalletScore, PerpWatchlist
from app.services.alerts.delivery import dispatch
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

log = logging.getLogger(__name__)

RULE_NAME = "perp_watch"
RULE_TYPE = "perp_watch"


def _ensure_rule(session) -> AlertRule:
    """Singleton AlertRule row that all perp_watch events FK to.

    Idempotent across concurrent first-time callers via ON CONFLICT DO NOTHING.
    """
    rule = session.execute(
        select(AlertRule).where(AlertRule.name == RULE_NAME)
    ).scalar_one_or_none()
    if rule is not None:
        return rule
    stmt = (
        pg_insert(AlertRule.__table__)
        .values(
            name=RULE_NAME,
            rule_type=RULE_TYPE,
            params={},
            channels=[{"type": "telegram"}],
            enabled=False,
        )
        .on_conflict_do_nothing(index_elements=["name"])
    )
    session.execute(stmt)
    session.commit()
    # After the upsert (either inserted by us or by a concurrent caller), the row exists.
    return session.execute(
        select(AlertRule).where(AlertRule.name == RULE_NAME)
    ).scalar_one()


def build_payload(
    event: dict,
    watch: PerpWatchlist,
    score: PerpWalletScore | None,
) -> dict[str, Any]:
    """Shape the alert payload. `event` is the decoded GMX event dict."""
    return {
        "wallet": event["account"],
        "label": watch.label,
        "event_kind": event["event_kind"],
        "market": event["market"],
        "side": event["side"],
        "size_usd": str(event["size_usd"]),
        "leverage": str(event["leverage"]),
        "price_usd": str(event["price_usd"]),
        "pnl_usd": None if event.get("pnl_usd") is None else str(event["pnl_usd"]),
        "tx_hash": event["tx_hash"],
        "score": None if score is None else {
            "win_rate": str(score.win_rate_90d),
            "trades": score.trades_90d,
            "avg_hold_secs": score.avg_hold_secs,
        },
    }


async def dispatch_perp_watch(
    http: httpx.AsyncClient,
    event: dict,
    watch: PerpWatchlist,
) -> None:
    """Format + deliver + persist a single perp watchlist alert."""
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rule = _ensure_rule(session)
        score = session.execute(
            select(PerpWalletScore).where(PerpWalletScore.wallet == event["account"].lower())
        ).scalar_one_or_none()
        payload = build_payload(event, watch, score)
        delivered = await dispatch(
            http,
            [{"type": "telegram"}],
            rule_name=watch.label or event["account"][:10],
            rule_type=RULE_TYPE,
            payload=payload,
        )
        session.add(AlertEvent(
            rule_id=rule.id,
            fired_at=event["ts"] if isinstance(event["ts"], datetime) else datetime.fromisoformat(event["ts"]),
            payload=payload,
            delivered=delivered,
        ))
        session.commit()
