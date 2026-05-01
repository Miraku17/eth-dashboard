"""Daily cron: drop wallet_clusters rows that are past their grace window.

We keep rows for `cluster_cache_ttl_days` past expiry as a stale-fallback
during Etherscan outages. After that window, they're permanently deleted.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.models import WalletCluster

log = logging.getLogger(__name__)


async def purge_expired_clusters(ctx: dict) -> int:
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=settings.cluster_cache_ttl_days)

    # Allow tests to inject a session without spinning up get_sessionmaker.
    test_session = ctx.get("_db_session_for_test") if isinstance(ctx, dict) else None
    if test_session is not None:
        result = test_session.execute(
            delete(WalletCluster).where(WalletCluster.ttl_expires_at < cutoff)
        )
        test_session.commit()
        n = result.rowcount or 0
    else:
        sessionmaker = ctx.get("sessionmaker") or get_sessionmaker()
        with sessionmaker() as session:
            result = session.execute(
                delete(WalletCluster).where(WalletCluster.ttl_expires_at < cutoff)
            )
            session.commit()
            n = result.rowcount or 0

    log.info("purged %d expired wallet_clusters rows", n)
    return n
