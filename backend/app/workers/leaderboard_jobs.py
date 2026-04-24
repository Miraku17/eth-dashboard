"""arq task entrypoint for the smart-money leaderboard Dune sync."""
import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy import select

from app.clients.dune import DUNE_BASE_URL, DuneClient, DuneExecutionError
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.models import PriceCandle
from app.core.sync_status import record_sync_ok
from app.services.leaderboard_sync import persist_snapshot

log = logging.getLogger(__name__)

WINDOW_DAYS = 30


def _latest_eth_price(session) -> Decimal | None:
    """Use the most recent 1h close as the window-end mark. None if unavailable."""
    row = session.execute(
        select(PriceCandle)
        .where(PriceCandle.symbol == "ETHUSDT", PriceCandle.timeframe == "1h")
        .order_by(PriceCandle.ts.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    return Decimal(str(row.close))


async def sync_smart_money_leaderboard(ctx: dict) -> dict:
    """Execute the Dune leaderboard query and persist a fresh snapshot.

    Skips cleanly when the query ID is not configured (matches existing
    flow-sync conventions). Leaves the previous snapshot in place on any
    error so the API keeps serving stale-but-valid data.
    """
    settings = get_settings()
    if not settings.dune_api_key:
        log.warning("DUNE_API_KEY not set — skipping leaderboard sync")
        return {"skipped": "no api key"}
    if settings.dune_query_id_smart_money_leaderboard == 0:
        log.info("leaderboard query ID not configured — skipping")
        return {"skipped": "not configured"}

    SessionLocal = get_sessionmaker()

    async with httpx.AsyncClient(base_url=DUNE_BASE_URL, timeout=600.0) as http:
        client = DuneClient(http, api_key=settings.dune_api_key)
        try:
            rows = await client.execute_and_fetch(
                settings.dune_query_id_smart_money_leaderboard,
                max_wait_s=600.0,
                performance="free",
            )
        except (DuneExecutionError, httpx.HTTPError) as e:
            log.error("smart-money leaderboard dune query failed: %s", e)
            return {"error": str(e)}

    with SessionLocal() as session:
        eth_price = _latest_eth_price(session)
        run_id = persist_snapshot(
            session,
            rows=rows,
            window_days=WINDOW_DAYS,
            window_end_eth_price=eth_price,
            snapshot_at=datetime.now(UTC),
        )

    if run_id is None:
        return {"skipped": "no rows returned"}

    record_sync_ok("smart_money")
    return {"run_id": str(run_id), "rows": len(rows)}
