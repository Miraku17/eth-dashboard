"""Realtime Alchemy WebSocket listener. Implementation lands in M3."""
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def main() -> None:
    log.info("realtime listener placeholder — implemented in M3")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
