"""Hourly order-flow aggregator (v4 — replaces Dune order_flow for
Uniswap V2 + V3 pools).

Pattern mirrors SupplyAggregator: in-memory accumulation per
(ts_bucket, dex, side), flush on hour rollover with additive
on_conflict_do_update so partial flushes (graceful shutdown mid-hour)
compose correctly.

USD value: weth_amount × current ETH price. The aggregator takes a
price-provider callable so the listener can pass an `_latest_eth_usd`
closure without coupling this module to Postgres.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import OrderFlow

SessionFactory = Callable[[], Session] | sessionmaker
PriceProvider = Callable[[], float | None]


class OrderFlowAggregator:
    """Buffers (dex, side) → (count, weth_total) for one hour, flushes to
    `order_flow` when the active hour changes."""

    def __init__(
        self,
        session_factory: SessionFactory,
        price_provider: PriceProvider,
    ) -> None:
        self._session_factory = session_factory
        self._price_provider = price_provider
        self._current_hour: datetime | None = None
        # (dex, side) -> (count, weth_total)
        self._buf: dict[tuple[str, str], tuple[int, float]] = {}

    def add(self, dex: str, side: str, weth_amount: float, ts: datetime) -> None:
        if side not in ("buy", "sell"):
            return
        if weth_amount <= 0:
            return
        hour = ts.replace(minute=0, second=0, microsecond=0)
        if self._current_hour is None:
            self._current_hour = hour
        elif hour != self._current_hour:
            self._flush_current()
            self._current_hour = hour
            self._buf = {}
        count, total = self._buf.get((dex, side), (0, 0.0))
        self._buf[(dex, side)] = (count + 1, total + weth_amount)

    def flush(self) -> None:
        if self._current_hour is not None:
            self._flush_current()
            self._buf = {}
            self._current_hour = None

    def _flush_current(self) -> None:
        if not self._buf or self._current_hour is None:
            return
        # Pricing is computed at flush time, not per-event, because flushes
        # are rare (hourly) and the listener's price-cache lookup is fine.
        # Inaccurate by at most ~1 hour of drift in volatile periods —
        # acceptable for an aggregate dashboard signal.
        eth_price = self._price_provider() or 0.0
        rows = []
        for (dex, side), (count, weth_total) in self._buf.items():
            rows.append(
                {
                    "ts_bucket": self._current_hour,
                    "dex": dex,
                    "side": side,
                    "usd_value": weth_total * eth_price,
                    "trade_count": count,
                }
            )
        stmt = pg_insert(OrderFlow).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_bucket", "dex", "side"],
            set_={
                # ADDITIVE for both — multiple flushes within the same hour
                # (graceful restart, etc.) compose cleanly.
                "usd_value": OrderFlow.usd_value + stmt.excluded.usd_value,
                "trade_count": OrderFlow.trade_count + stmt.excluded.trade_count,
            },
        )
        with self._session_factory() as session:
            session.execute(stmt)
            session.commit()
