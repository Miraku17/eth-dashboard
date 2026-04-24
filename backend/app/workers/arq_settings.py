import httpx
from arq.connections import RedisSettings
from arq.cron import cron

from app.clients.binance import BINANCE_BASE_URL
from app.core.config import get_settings
from app.workers.alert_jobs import evaluate_alerts
from app.workers.derivatives_jobs import sync_derivatives
from app.workers.flow_jobs import sync_dune_flows
from app.workers.price_jobs import backfill_price_history, sync_price_latest


async def startup(ctx: dict) -> None:
    ctx["http"] = httpx.AsyncClient(base_url=BINANCE_BASE_URL, timeout=15.0)
    await ctx["redis"].enqueue_job("backfill_price_history")
    await ctx["redis"].enqueue_job("sync_dune_flows")
    await ctx["redis"].enqueue_job("sync_derivatives")


async def shutdown(ctx: dict) -> None:
    await ctx["http"].aclose()


_settings = get_settings()


def _dune_cron_kwargs() -> dict:
    interval = _settings.dune_sync_interval_min
    if interval < 60:
        return {"minute": set(range(0, 60, max(1, interval)))}
    hours = set(range(0, 24, max(1, interval // 60)))
    return {"minute": {0}, "hour": hours}


class WorkerSettings:
    functions = [
        backfill_price_history,
        sync_price_latest,
        sync_dune_flows,
        evaluate_alerts,
        sync_derivatives,
    ]
    cron_jobs = [
        cron(sync_price_latest, minute=set(range(0, 60)), run_at_startup=False),
        cron(sync_dune_flows, **_dune_cron_kwargs(), run_at_startup=False),
        cron(evaluate_alerts, minute=set(range(0, 60)), run_at_startup=False),
        # Derivatives: once per hour, on the top of the hour. Funding rates
        # only change every 8h on most venues; hourly is plenty.
        cron(sync_derivatives, minute={5}, run_at_startup=False),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
