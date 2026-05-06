"""Writer for `onchain_perp_event` rows — bulk-upsert with idempotent dedup.

Mirrors swap_writer.py: stateless wrt buffering, the caller hands a list
per flush tick. ON CONFLICT DO NOTHING on (tx_hash, log_index) keeps
restarts and reorgs idempotent.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import OnchainPerpEvent
from app.realtime.gmx_v2_decoder import GmxEvent

SessionFactory = Callable[[], Session] | sessionmaker


class PerpWriter:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def write(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        stmt = pg_insert(OnchainPerpEvent).values(rows).on_conflict_do_nothing(
            index_elements=["tx_hash", "log_index"]
        )
        with self._session_factory() as session:
            result = session.execute(stmt)
            session.commit()
        return getattr(result, "rowcount", 0) or 0


def make_row(event: GmxEvent, *, ts: datetime, tx_hash: str, log_index: int) -> dict:
    """Translate a decoded GmxEvent into an `onchain_perp_event` row.

    `ts` comes from the block header (decoded by the listener). The
    decoder itself is timestamp-free since payloads don't carry one.
    """
    return {
        "ts": ts,
        "venue": event.venue,
        "account": event.account.lower(),
        "market": event.market,
        "event_kind": event.event_kind,
        "side": event.side,
        "size_usd": event.size_usd,
        "size_after_usd": event.size_after_usd,
        "collateral_usd": event.collateral_usd,
        "leverage": event.leverage,
        "price_usd": event.price_usd,
        "pnl_usd": event.pnl_usd,
        "tx_hash": tx_hash,
        "log_index": log_index,
    }
