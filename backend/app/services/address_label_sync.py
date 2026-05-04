"""Idempotent seeder for the curated address-label registry.

Runs at worker startup. Inserts new rows, updates rows whose category or
label drifted since last seed, leaves heuristic / etherscan-imported rows
untouched. Tracked by `_SEED_REVISION` in `address_labels.py`: when that
number bumps the seeder re-upserts; otherwise it's a one-line check.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import AddressLabel
from app.services.address_labels import CURATED_LABELS, get_seed_revision

log = logging.getLogger(__name__)

# Stored as a one-row label entry under this sentinel "address" so we can
# detect seed-revision drift with a single point lookup. The address is a
# zero-padded sentinel that can never collide with a real Ethereum address
# (real ones don't end in this exact pattern by chance — and even if they
# did, the row's category/label clearly mark it as internal metadata).
_SEED_REVISION_KEY = "0x000000000000000000000000000000000000fffe"


def seed_address_labels(session: Session) -> dict:
    """Upsert curated labels into the `address_label` table.

    Idempotency: stores the current `_SEED_REVISION` under a sentinel
    address. If that matches what's already in the DB, this is a no-op.
    Otherwise upserts every curated row + bumps the stored revision.

    Returns a small dict with the action taken — useful for logs and
    a quick health check.
    """
    revision = get_seed_revision()
    sentinel = session.get(AddressLabel, _SEED_REVISION_KEY)
    if sentinel is not None and sentinel.confidence == revision:
        return {"action": "skipped", "revision": revision, "rows": 0}

    now = datetime.now(UTC)
    rows = [
        {
            "address": e.address.lower(),
            "category": e.category,
            "label": e.label,
            "source": "curated",
            "confidence": 100,
            "updated_at": now,
        }
        for e in CURATED_LABELS
    ]

    # Only update curated entries on conflict — heuristic / etherscan rows
    # have a different `source` and we deliberately leave them alone so
    # the operator can override curated guesses. The WHERE clause on the
    # update enforces this at the SQL level.
    stmt = pg_insert(AddressLabel).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["address"],
        set_={
            "category": stmt.excluded.category,
            "label": stmt.excluded.label,
            "source": stmt.excluded.source,
            "confidence": stmt.excluded.confidence,
            "updated_at": stmt.excluded.updated_at,
        },
        where=AddressLabel.source == "curated",
    )
    session.execute(stmt)

    # Sentinel row tracks current seed revision. confidence is overloaded
    # to hold the revision number (saves an extra column for a single value).
    sentinel_stmt = pg_insert(AddressLabel).values(
        {
            "address": _SEED_REVISION_KEY,
            "category": "smart_contract",
            "label": "[internal] curated seed revision marker",
            "source": "curated",
            "confidence": revision,
            "updated_at": now,
        }
    )
    sentinel_stmt = sentinel_stmt.on_conflict_do_update(
        index_elements=["address"],
        set_={
            "confidence": sentinel_stmt.excluded.confidence,
            "updated_at": sentinel_stmt.excluded.updated_at,
        },
    )
    session.execute(sentinel_stmt)
    session.commit()

    log.info("seeded address_label: %d rows at revision %d", len(rows), revision)
    return {"action": "seeded", "revision": revision, "rows": len(rows)}
