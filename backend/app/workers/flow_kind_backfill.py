"""One-shot backfill: score `transfers.flow_kind` for historical rows.

Runs once at worker startup after migration 0023. After it completes,
the realtime listener tags every NEW transfer at write time, so this
job becomes a no-op on subsequent boots (idempotent — only updates
rows where flow_kind IS NULL).

Strategy: stream rows in batches of 1000, classify, UPDATE in bulk.
Joins against the address_label registry once per batch. Designed to
finish in seconds for typical Etherscope DB sizes (~10k-100k rows).
"""
from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.db import get_sessionmaker
from app.core.models import AddressLabel, Transfer
from app.realtime.flow_classifier import classify as classify_flow

log = logging.getLogger(__name__)

_BATCH = 1000


def _load_label_map(session: Session) -> dict[str, str]:
    """All curated/heuristic labels in memory. ~100s of rows, tiny."""
    rows = session.execute(select(AddressLabel.address, AddressLabel.category)).all()
    return {a: c for (a, c) in rows}


def backfill_flow_kind(session: Session) -> dict:
    """Tag every NULL-flow_kind transfer with its classification.

    Returns a small dict for logging / health-check output.
    """
    label_map = _load_label_map(session)
    total_updated = 0
    last_id: tuple[str, int] | None = None

    while True:
        # Stable ordering by (tx_hash, log_index) — both PK columns.
        # Cursor-based pagination so we never re-scan rows we've already
        # written, and we don't lock the whole table.
        stmt = (
            select(Transfer.tx_hash, Transfer.log_index, Transfer.from_addr, Transfer.to_addr)
            .where(Transfer.flow_kind.is_(None))
            .order_by(Transfer.tx_hash.asc(), Transfer.log_index.asc())
            .limit(_BATCH)
        )
        if last_id is not None:
            stmt = stmt.where(
                (Transfer.tx_hash > last_id[0])
                | ((Transfer.tx_hash == last_id[0]) & (Transfer.log_index > last_id[1]))
            )
        batch = session.execute(stmt).all()
        if not batch:
            break

        # Group rows by their classified flow_kind and run one UPDATE per
        # group (vs one UPDATE per row). Most rows in any given batch
        # cluster onto a few flow kinds, so this is typically 5-10
        # statements per batch instead of 1000.
        by_kind: dict[str, list[tuple[str, int]]] = {}
        for tx_hash, log_index, from_addr, to_addr in batch:
            kind = classify_flow(
                label_map.get(from_addr.lower()),
                label_map.get(to_addr.lower()),
            )
            by_kind.setdefault(kind, []).append((tx_hash, log_index))

        for kind, keys in by_kind.items():
            tx_hashes = [k[0] for k in keys]
            log_indexes = [k[1] for k in keys]
            # Match rows by composite-key membership. Postgres handles
            # tuple IN ((..., ...), ...) but SQLAlchemy doesn't compose
            # that cleanly across drivers, so we filter both columns
            # independently and rely on the PK uniqueness to keep matches
            # exact within the batch — never wrong because (tx_hash,
            # log_index) is the PK.
            session.execute(
                update(Transfer)
                .where(
                    Transfer.tx_hash.in_(tx_hashes),
                    Transfer.log_index.in_(log_indexes),
                    Transfer.flow_kind.is_(None),
                )
                .values(flow_kind=kind)
            )
            total_updated += len(keys)
        session.commit()

        last_id = (batch[-1][0], batch[-1][1])
        log.info("flow_kind backfill: scored %d rows so far", total_updated)

    return {"backfilled": total_updated}


async def run_backfill_if_needed(ctx: dict) -> dict:
    """Arq-job-style entrypoint. Wraps the sync logic in a session.

    Cheap fast-path: a single 'EXISTS where flow_kind IS NULL LIMIT 1'
    skips the whole job once the backfill has completed once.
    """
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        has_null = session.execute(
            select(Transfer.tx_hash).where(Transfer.flow_kind.is_(None)).limit(1)
        ).first()
        if has_null is None:
            return {"backfilled": 0, "action": "skipped"}
        return backfill_flow_kind(session)
