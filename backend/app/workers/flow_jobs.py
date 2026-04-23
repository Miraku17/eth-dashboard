"""arq task entrypoints for Dune flow sync."""
import logging

import httpx

from app.clients.dune import DUNE_BASE_URL, DuneClient, DuneExecutionError
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.services.flow_sync import (
    upsert_exchange_flows,
    upsert_onchain_volume,
    upsert_stablecoin_flows,
)

log = logging.getLogger(__name__)


async def sync_dune_flows(ctx: dict) -> dict:
    """Execute and fetch all 3 Dune queries, upsert into their respective tables.

    Skips any query whose ID is 0 (not configured). Logs execution errors but continues
    so one broken query doesn't halt the rest.
    """
    settings = get_settings()
    if not settings.dune_api_key:
        log.warning("DUNE_API_KEY not set — skipping flow sync")
        return {"skipped": "no api key"}

    SessionLocal = get_sessionmaker()
    results: dict[str, int | str] = {}

    async with httpx.AsyncClient(base_url=DUNE_BASE_URL, timeout=300.0) as http:
        client = DuneClient(http, api_key=settings.dune_api_key)

        jobs = [
            ("exchange_flows", settings.dune_query_id_exchange_flows, upsert_exchange_flows),
            ("stablecoin_flows", settings.dune_query_id_stablecoin_supply, upsert_stablecoin_flows),
            ("onchain_volume", settings.dune_query_id_onchain_volume, upsert_onchain_volume),
        ]

        for name, query_id, upsert_fn in jobs:
            if query_id == 0:
                log.info("skipping %s: query ID not configured", name)
                results[name] = "not configured"
                continue
            try:
                rows = await client.execute_and_fetch(query_id)
            except (DuneExecutionError, httpx.HTTPError) as e:
                log.error("dune sync %s failed: %s", name, e)
                results[name] = f"error: {e}"
                continue
            with SessionLocal() as session:
                n = upsert_fn(session, rows)
            log.info("synced %s: %d rows", name, n)
            results[name] = n

    return results
