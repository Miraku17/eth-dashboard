"""arq task entrypoints for Dune flow sync."""
import logging

import httpx

from app.clients.dune import DUNE_BASE_URL, DuneClient, DuneExecutionError
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.sync_status import record_sync_ok
from app.services.flow_sync import (
    upsert_bridge_flows,
    upsert_exchange_flows,
    upsert_onchain_volume,
    upsert_order_flow,
    upsert_stablecoin_flows,
    upsert_staking_flows,
    upsert_staking_flows_by_entity,
    upsert_volume_buckets,
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
            # v4: stablecoin_flows migrated off Dune. The realtime listener's
            # SupplyAggregator detects Mint (from=0x0) and Burn (to=0x0) Transfer
            # events on the 15 tracked stables and flushes hourly to the same
            # `stablecoin_flows` table. DUNE_QUERY_ID_STABLECOIN_SUPPLY preserved
            # for rollback. Saves ~720 Dune executions/month.
            # ("stablecoin_flows", settings.dune_query_id_stablecoin_supply, upsert_stablecoin_flows),
            # v4: onchain_volume migrated off Dune. The /api/flows/onchain-volume
            # endpoint now reads from `realtime_volume` (per-minute USD by asset,
            # populated by the realtime listener) rolled up to hourly buckets.
            # The Dune query is preserved in DUNE_QUERY_ID_ONCHAIN_VOLUME for
            # rollback but no longer executed. Saves ~720 Dune executions/month.
            # ("onchain_volume", settings.dune_query_id_onchain_volume, upsert_onchain_volume),
            # v4: staking_flows migrated off Dune. The new sync_beacon_flows
            # cron walks newly-finalized slots from Lighthouse every 5 min,
            # sums deposits + withdrawals, classifies withdrawals as partial
            # (rewards) or full (exit) by amount threshold, and upserts hourly
            # rollups into the same staking_flows table. DUNE_QUERY_ID_STAKING_FLOWS
            # preserved for rollback. Saves ~720 Dune executions/month.
            # ("staking_flows", settings.dune_query_id_staking_flows, upsert_staking_flows),
            ("staking_flows_by_entity", settings.dune_query_id_staking_flows_by_entity, upsert_staking_flows_by_entity),
            ("bridge_flows", settings.dune_query_id_bridge_flows, upsert_bridge_flows),
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

    # Record sync completion only if at least one query succeeded. A run where
    # every query errored shouldn't flip the health indicator green.
    if any(isinstance(v, int) for v in results.values()):
        record_sync_ok("dune_flows")

    return results


async def sync_order_flow(ctx: dict) -> dict:
    """Standalone cron for order-flow at a lower cadence than the main flow
    sync, so we don't blow the Dune free-tier credit budget."""
    settings = get_settings()
    if not settings.dune_api_key:
        log.warning("DUNE_API_KEY not set — skipping order-flow sync")
        return {"skipped": "no api key"}
    if settings.dune_query_id_order_flow == 0:
        log.info("order-flow query ID not configured — skipping")
        return {"skipped": "not configured"}

    SessionLocal = get_sessionmaker()
    async with httpx.AsyncClient(base_url=DUNE_BASE_URL, timeout=300.0) as http:
        client = DuneClient(http, api_key=settings.dune_api_key)
        try:
            rows = await client.execute_and_fetch(settings.dune_query_id_order_flow)
        except (DuneExecutionError, httpx.HTTPError) as e:
            log.error("order-flow dune query failed: %s", e)
            return {"error": str(e)}

    with SessionLocal() as session:
        n = upsert_order_flow(session, rows)
    record_sync_ok("order_flow")
    log.info("synced order_flow: %d rows", n)
    return {"order_flow": n}


async def sync_volume_buckets(ctx: dict) -> dict:
    """Sync hourly trade-size buckets (retail/mid/large/whale) from Dune.
    Same source as order-flow (`dex.trades` filtered to WETH); shares the
    8h cadence to keep credit usage predictable."""
    settings = get_settings()
    if not settings.dune_api_key:
        log.warning("DUNE_API_KEY not set — skipping volume-buckets sync")
        return {"skipped": "no api key"}
    if settings.dune_query_id_volume_buckets == 0:
        log.info("volume-buckets query ID not configured — skipping")
        return {"skipped": "not configured"}

    SessionLocal = get_sessionmaker()
    async with httpx.AsyncClient(base_url=DUNE_BASE_URL, timeout=300.0) as http:
        client = DuneClient(http, api_key=settings.dune_api_key)
        try:
            rows = await client.execute_and_fetch(settings.dune_query_id_volume_buckets)
        except (DuneExecutionError, httpx.HTTPError) as e:
            log.error("volume-buckets dune query failed: %s", e)
            return {"error": str(e)}

    with SessionLocal() as session:
        n = upsert_volume_buckets(session, rows)
    record_sync_ok("volume_buckets")
    log.info("synced volume_buckets: %d rows", n)
    return {"volume_buckets": n}
