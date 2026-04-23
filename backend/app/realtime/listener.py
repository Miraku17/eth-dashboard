"""Alchemy WebSocket listener — detects large ETH + stablecoin transfers.

Subscribes to `newHeads` and, for each new block, pulls the block (with
transactions) and the ERC-20 Transfer logs for the tokens we track, then
persists rows above threshold into the `transfers` table.

Run via `python -m app.realtime.listener` (docker-compose `realtime` service).
"""
import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime

import websockets
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.models import PriceCandle, Transfer
from app.realtime.parser import (
    WhaleTransfer,
    block_timestamp,
    parse_erc20_log,
    parse_native_tx,
)
from app.realtime.tokens import STABLES, TRANSFER_TOPIC

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("realtime")

RECONNECT_DELAY_S = 5.0


def _latest_eth_usd(session: Session) -> float | None:
    row = session.execute(
        select(PriceCandle)
        .where(PriceCandle.symbol == "ETHUSDT", PriceCandle.timeframe == "1m")
        .order_by(PriceCandle.ts.desc())
        .limit(1)
    ).scalar_one_or_none()
    return float(row.close) if row else None


def _persist(session: Session, rows: list[WhaleTransfer]) -> int:
    if not rows:
        return 0
    stmt = insert(Transfer).values([
        {
            "tx_hash": r.tx_hash,
            "log_index": r.log_index,
            "block_number": r.block_number,
            "ts": r.ts,
            "from_addr": r.from_addr,
            "to_addr": r.to_addr,
            "asset": r.asset,
            "amount": r.amount,
            "usd_value": r.usd_value,
        }
        for r in rows
    ])
    stmt = stmt.on_conflict_do_nothing(index_elements=["tx_hash", "log_index"])
    result = session.execute(stmt)
    session.commit()
    return result.rowcount or 0


class AlchemyClient:
    def __init__(self, ws) -> None:
        self._ws = ws
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._subs: dict[str, asyncio.Queue] = {}

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def call(self, method: str, params: list) -> dict:
        rid = self._next_id()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        await self._ws.send(json.dumps(payload))
        return await fut

    async def subscribe(self, params: list) -> asyncio.Queue:
        res = await self.call("eth_subscribe", params)
        sub_id = res["result"]
        q: asyncio.Queue = asyncio.Queue()
        self._subs[sub_id] = q
        return q

    async def pump(self) -> None:
        async for raw in self._ws:
            msg = json.loads(raw)
            if "id" in msg and msg["id"] in self._pending:
                self._pending.pop(msg["id"]).set_result(msg)
            elif msg.get("method") == "eth_subscription":
                sub_id = msg["params"]["subscription"]
                q = self._subs.get(sub_id)
                if q is not None:
                    await q.put(msg["params"]["result"])


async def _process_block(
    client: AlchemyClient,
    block_number: int,
    sessionmaker,
    thresholds: tuple[float, float],
) -> None:
    threshold_eth, threshold_usd = thresholds
    hex_bn = hex(block_number)

    block_res = await client.call("eth_getBlockByNumber", [hex_bn, True])
    block = block_res.get("result")
    if not block:
        return
    ts = block_timestamp(block)

    token_addrs = [t.address for t in STABLES]
    logs_res = await client.call(
        "eth_getLogs",
        [{
            "fromBlock": hex_bn,
            "toBlock": hex_bn,
            "address": token_addrs,
            "topics": [TRANSFER_TOPIC],
        }],
    )
    logs = logs_res.get("result") or []

    rows: list[WhaleTransfer] = []
    with sessionmaker() as session:
        eth_usd = _latest_eth_usd(session)

    for tx in block.get("transactions") or []:
        row = parse_native_tx(
            tx,
            block_number=block_number,
            block_ts=ts,
            eth_usd=eth_usd,
            threshold_eth=threshold_eth,
        )
        if row:
            rows.append(row)

    for lg in logs:
        row = parse_erc20_log(lg, block_ts=ts, threshold_usd=threshold_usd)
        if row:
            rows.append(row)

    if rows:
        with sessionmaker() as session:
            inserted = _persist(session, rows)
            log.info(
                "block=%d detected=%d persisted=%d eth_usd=%s",
                block_number, len(rows), inserted, eth_usd,
            )


async def run_once(ws_url: str, sessionmaker, thresholds: tuple[float, float]) -> None:
    async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
        client = AlchemyClient(ws)
        pump_task = asyncio.create_task(client.pump())
        try:
            heads = await client.subscribe(["newHeads"])
            log.info("subscribed to newHeads")
            while True:
                head = await heads.get()
                bn = int(head["number"], 16)
                try:
                    await _process_block(client, bn, sessionmaker, thresholds)
                except Exception:
                    log.exception("block %d processing failed", bn)
        finally:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump_task


async def main() -> None:
    settings = get_settings()
    if not settings.alchemy_ws_url:
        log.warning("ALCHEMY_API_KEY not set — realtime listener idling")
        while True:
            await asyncio.sleep(3600)

    sessionmaker = get_sessionmaker()
    thresholds = (settings.whale_eth_threshold, settings.whale_stable_threshold_usd)
    log.info("starting realtime listener thresholds eth>=%s stable_usd>=%s at %s",
             thresholds[0], thresholds[1], datetime.now(UTC).isoformat())

    while True:
        try:
            await run_once(settings.alchemy_ws_url, sessionmaker, thresholds)
        except Exception:
            log.exception("listener crashed, reconnecting in %.0fs", RECONNECT_DELAY_S)
            await asyncio.sleep(RECONNECT_DELAY_S)


if __name__ == "__main__":
    asyncio.run(main())
