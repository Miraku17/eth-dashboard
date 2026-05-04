"""Per-swap row writer — captures every decoded Swap event the listener
sees, alongside the originating EOA, into the `dex_swap` table.

Used as input by the daily wallet-scoring cron (FIFO PnL + win rate +
volume rank). The aggregators (order_flow, volume_buckets) keep their
hourly rollup roles; this is the row-level capture for analytics that
need to know WHO did the swap.

Flush pattern: each block's swaps are batched and bulk-inserted at the
end of the block-processing loop. ON CONFLICT DO NOTHING on
(tx_hash, log_index) keeps reorgs and listener restarts idempotent.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import DexSwap

SessionFactory = Callable[[], Session] | sessionmaker


class SwapWriter:
    """Stateless wrt buffering — caller hands a list per block, we just
    bulk-upsert. Kept as a class for symmetry with the other aggregators
    (uniform construction in the listener)."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def write(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        stmt = pg_insert(DexSwap).values(rows).on_conflict_do_nothing(
            index_elements=["tx_hash", "log_index"]
        )
        with self._session_factory() as session:
            result = session.execute(stmt)
            session.commit()
        # rowcount can be -1 on ON CONFLICT DO NOTHING in some drivers;
        # callers shouldn't rely on the return value for correctness, only
        # for log-line freshness.
        return getattr(result, "rowcount", 0) or 0


def make_row(
    *,
    tx_hash: str,
    log_index: int,
    ts: datetime,
    wallet: str,
    dex: str,
    side: str,
    weth_amount: float,
    usd_value: float,
) -> dict:
    """Builder — explicit kwargs avoid mistaken positional argument order.

    The listener calls this once per decoded SwapEvent + tx-from lookup.
    """
    return {
        "tx_hash": tx_hash,
        "log_index": log_index,
        "ts": ts,
        "wallet": wallet.lower(),
        "dex": dex,
        "side": side,
        "weth_amount": weth_amount,
        "usd_value": usd_value,
    }
