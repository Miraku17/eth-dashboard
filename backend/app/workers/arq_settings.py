from arq.connections import RedisSettings

from app.core.config import get_settings


async def startup(ctx: dict) -> None:
    ctx["started"] = True


async def shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    functions: list = []  # populated in M1+
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
