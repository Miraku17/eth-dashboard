from arq.connections import RedisSettings

from app.core.config import get_settings


async def startup(ctx: dict) -> None:
    ctx["started"] = True


async def shutdown(ctx: dict) -> None:
    pass


async def noop(ctx: dict) -> str:
    return "ok"


class WorkerSettings:
    # arq rejects an empty functions list; `noop` is a placeholder until M1 adds real jobs.
    functions = [noop]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
