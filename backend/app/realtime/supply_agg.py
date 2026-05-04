"""Hourly stablecoin supply aggregator (v4 — replaces Dune stablecoin_supply).

Lives in-process inside the realtime listener. The listener calls `add()`
on every Mint or Burn transfer it observes (Transfer events where one
side is the zero address — see `parser.extract_mint_burn`). When the
hour boundary rolls over we batch-upsert the previous hour's per-asset
totals to the `stablecoin_flows` table — same shape the Dune-fed query
used to populate, so the panel reads unchanged.

Mirrors `MinuteAggregator` exactly in pattern; differences:
  * Hourly buckets instead of per-minute.
  * Tracks two directions per (asset, hour) — 'mint' and 'burn'.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import StablecoinFlow

SessionFactory = Callable[[], Session] | sessionmaker


class SupplyAggregator:
    """Buffers one hour of per-(asset, direction) USD totals in memory,
    flushing to Postgres when the active hour changes."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._current_hour: datetime | None = None
        # (asset, direction) -> usd_total
        self._buf: dict[tuple[str, str], float] = {}

    def add(self, asset: str, direction: str, usd_value: float, ts: datetime) -> None:
        """Add a single mint/burn event to the active hour. If `ts` lands
        in a new hour, flush the previous one first."""
        if direction not in ("mint", "burn"):
            return
        hour = ts.replace(minute=0, second=0, microsecond=0)
        if self._current_hour is None:
            self._current_hour = hour
        elif hour != self._current_hour:
            self._flush_current()
            self._current_hour = hour
            self._buf = {}
        key = (asset, direction)
        self._buf[key] = self._buf.get(key, 0.0) + usd_value

    def flush(self) -> None:
        """Persist any pending bucket. Called on listener shutdown."""
        if self._current_hour is not None:
            self._flush_current()
            self._buf = {}
            self._current_hour = None

    def _flush_current(self) -> None:
        if not self._buf or self._current_hour is None:
            return
        rows = [
            {
                "asset": asset,
                "direction": direction,
                "ts_bucket": self._current_hour,
                # The supply aggregator is incremental — accumulate into
                # whatever's already there for this (asset, direction, hour).
                # The on-conflict path adds the buffered delta to the stored
                # value rather than overwriting, so partial flushes (e.g. on
                # graceful shutdown mid-hour) compose correctly.
                "usd_value": total,
            }
            for (asset, direction), total in self._buf.items()
        ]
        stmt = pg_insert(StablecoinFlow).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["asset", "direction", "ts_bucket"],
            set_={
                "usd_value": StablecoinFlow.usd_value + stmt.excluded.usd_value,
            },
        )
        with self._session_factory() as session:
            session.execute(stmt)
            session.commit()
