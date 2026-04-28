import httpx
from arq.connections import RedisSettings
from arq.cron import cron

from app.clients.binance import BINANCE_BASE_URL
from app.core.config import get_settings
from app.workers.alert_jobs import evaluate_alerts
from app.workers.derivatives_jobs import sync_derivatives
from app.workers.flow_jobs import sync_dune_flows, sync_order_flow
from app.workers.leaderboard_jobs import sync_smart_money_leaderboard
from app.workers.pending_cleanup import cleanup_pending_transfers
from app.workers.price_jobs import backfill_price_history, sync_price_latest


async def startup(ctx: dict) -> None:
    ctx["http"] = httpx.AsyncClient(base_url=BINANCE_BASE_URL, timeout=15.0)
    await ctx["redis"].enqueue_job("backfill_price_history")
    await ctx["redis"].enqueue_job("sync_dune_flows")
    await ctx["redis"].enqueue_job("sync_derivatives")
    await ctx["redis"].enqueue_job("sync_order_flow")
    await ctx["redis"].enqueue_job("sync_smart_money_leaderboard")


async def shutdown(ctx: dict) -> None:
    await ctx["http"].aclose()


_settings = get_settings()


def _cron_from_minutes(interval_min: int) -> dict:
    if interval_min < 60:
        return {"minute": set(range(0, 60, max(1, interval_min)))}
    hours = set(range(0, 24, max(1, interval_min // 60)))
    return {"minute": {0}, "hour": hours}


def _dune_cron_kwargs() -> dict:
    return _cron_from_minutes(_settings.dune_sync_interval_min)


def _order_flow_cron_kwargs() -> dict:
    # Offset by 10 minutes so we don't collide with the main Dune sync window.
    base = _cron_from_minutes(_settings.dune_order_flow_interval_min)
    base["minute"] = {10}
    return base


class WorkerSettings:
    functions = [
        backfill_price_history,
        sync_price_latest,
        sync_dune_flows,
        evaluate_alerts,
        sync_derivatives,
        sync_order_flow,
        sync_smart_money_leaderboard,
        cleanup_pending_transfers,
    ]
    cron_jobs = [
        cron(sync_price_latest, minute=set(range(0, 60)), run_at_startup=False),
        cron(sync_dune_flows, **_dune_cron_kwargs(), run_at_startup=False),
        cron(evaluate_alerts, minute=set(range(0, 60)), run_at_startup=False),
        # Derivatives: once per hour, on the top of the hour. Funding rates
        # only change every 8h on most venues; hourly is plenty.
        cron(sync_derivatives, minute={5}, run_at_startup=False),
        # Order flow: 8h cadence by default (every 3rd Dune slot) to keep
        # the free-tier credit budget healthy.
        cron(sync_order_flow, **_order_flow_cron_kwargs(), run_at_startup=False),
        # Smart-money leaderboard: once a day at 03:00 UTC. The query is
        # meaningfully heavier than order-flow (30d vs 7d window), so a
        # single refresh per day keeps us inside the Dune free-tier budget.
        cron(sync_smart_money_leaderboard, hour={3}, minute={0}, run_at_startup=False),
        # Pending whale cleanup: every minute, drops rows >30 min old or now-confirmed.
        cron(cleanup_pending_transfers, minute=set(range(0, 60)), run_at_startup=False),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
