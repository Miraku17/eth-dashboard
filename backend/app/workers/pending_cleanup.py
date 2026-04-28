"""Periodic job: drop expired or now-confirmed pending whale rows."""
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_sessionmaker

log = logging.getLogger("workers.pending_cleanup")

EXPIRY_MINUTES = 30


def _cleanup_pending(session: Session) -> int:
    res = session.execute(
        text(
            """
            DELETE FROM pending_transfers
            WHERE seen_at < NOW() - make_interval(mins => :minutes)
               OR tx_hash IN (
                   SELECT tx_hash FROM transfers WHERE ts > NOW() - INTERVAL '1 hour'
               )
            """
        ),
        {"minutes": EXPIRY_MINUTES},
    )
    session.commit()
    return res.rowcount or 0


async def cleanup_pending_transfers(ctx: dict) -> dict:
    sessionmaker = ctx.get("sessionmaker") or get_sessionmaker()
    with sessionmaker() as session:
        deleted = _cleanup_pending(session)
    log.info("pending_cleanup deleted=%d", deleted)
    return {"deleted": deleted}
