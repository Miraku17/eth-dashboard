"""arq task — fetch + persist derivatives snapshots from every exchange."""
import asyncio
import logging

import httpx

from app.clients.derivatives import FETCHERS
from app.core.db import get_sessionmaker
from app.core.sync_status import record_sync_ok
from app.services.derivatives_sync import upsert_snapshot

log = logging.getLogger(__name__)


async def sync_derivatives(ctx: dict) -> dict:
    """Hit each exchange in parallel; persist anything that came back. An
    individual exchange failure is logged but doesn't fail the whole run."""
    SessionLocal = get_sessionmaker()
    results: dict[str, int | str] = {}

    async with httpx.AsyncClient() as http:
        tasks = {
            name: asyncio.create_task(fetcher(http)) for name, fetcher in FETCHERS.items()
        }
        snaps = {}
        for name, task in tasks.items():
            try:
                snaps[name] = await task
                results[name] = "ok"
            except Exception as e:
                log.warning("derivatives %s fetch failed: %s", name, e)
                results[name] = f"error: {e}"

    if snaps:
        with SessionLocal() as session:
            for snap in snaps.values():
                upsert_snapshot(session, snap)
        record_sync_ok("derivatives")

    log.info("derivatives sync: %s", results)
    return results
