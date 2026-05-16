"""Redis-backed cache of the perp watchlist for the realtime hot path.

Primary invalidation is via Redis pub/sub on `perp_watchlist:invalidate`.
A 30s TTL is a safety net so the listener self-heals if it ever misses a
publish (e.g. transient Redis disconnect).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.models import PerpWatchlist

log = logging.getLogger(__name__)

INVALIDATE_CHANNEL = "perp_watchlist:invalidate"
CACHE_TTL_SECONDS = 30


class PerpWatchlistCache:
    """In-process watchlist (hex address → min_notional_usd Decimal).

    Refreshed on TTL expiry and on pub/sub invalidation.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._entries: dict[str, Decimal] = {}
        self._loaded_at: float = 0.0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        await self._reload()
        asyncio.create_task(self._subscribe_invalidations())

    async def lookup(self, account: str) -> Decimal | None:
        """Return the min_notional_usd floor if `account` is watched, else None."""
        if time.monotonic() - self._loaded_at > CACHE_TTL_SECONDS:
            await self._reload()
        return self._entries.get(account.lower())

    async def _reload(self) -> None:
        async with self._lock:
            SessionLocal = get_sessionmaker()
            with SessionLocal() as session:
                rows = session.execute(select(PerpWatchlist)).scalars().all()
            self._entries = {r.wallet.lower(): r.min_notional_usd for r in rows}
            self._loaded_at = time.monotonic()
        log.info("perp_watchlist_cache: %d entries loaded", len(self._entries))

    async def _subscribe_invalidations(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(INVALIDATE_CHANNEL)
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                await self._reload()
            except Exception:
                log.exception("perp_watchlist_cache reload failed")


async def publish_invalidate(redis: Redis) -> None:
    """Called by the CRUD endpoints after every watchlist mutation."""
    await redis.publish(INVALIDATE_CHANNEL, json.dumps({"ts": time.time()}))
