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
from app.core.models import NetworkActivity, PriceCandle, Transfer
from app.realtime.mempool import run_mempool_loop
from app.realtime.parser import (
    NetworkPoint,
    WhaleTransfer,
    block_timestamp,
    extract_network_activity,
    parse_erc20_log,
    parse_native_tx,
)
from app.realtime.tokens import ALL_TRACKED_ADDRESSES, TRANSFER_TOPIC

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("realtime")

RECONNECT_DELAY_S = 5.0
# If we don't receive a `newHeads` event in this many seconds, assume the WS
# is silently dead (Alchemy occasionally leaves the socket open but stops
# delivering messages) and tear it down so the outer reconnect loop fires.
# Mainnet blocks every ~12s, so 60s allows several missed blocks of slack
# before we flag the stream as stalled.
HEAD_STALL_TIMEOUT_S = 60.0
# Bound every JSON-RPC call so a silently-dead WS can't park us on a future
# that will never resolve. Without this, a mid-block hang skips the outer
# head-stall watchdog because we never get back to awaiting the head queue.
RPC_CALL_TIMEOUT_S = 30.0


async def next_head(queue: asyncio.Queue, timeout: float) -> dict | None:
    """Wait for the next `newHeads` payload, returning None on stall."""
    try:
        return await asyncio.wait_for(queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None


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
    # RETURNING gives us a real count of rows that were actually inserted
    # (vs skipped by ON CONFLICT). Plain rowcount on ON CONFLICT DO NOTHING
    # comes back as -1 in psycopg, which made the log say "persisted=-1".
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["tx_hash", "log_index"],
    ).returning(Transfer.tx_hash)
    result = session.execute(stmt)
    inserted = len(result.all())
    session.commit()
    return inserted


def _persist_network(session: Session, np: NetworkPoint) -> None:
    """Upsert on ts — two blocks with the same second (rare) collapse."""
    stmt = insert(NetworkActivity).values(
        ts=np.ts,
        tx_count=np.tx_count,
        gas_price_gwei=np.gas_price_gwei,
        base_fee=np.base_fee_gwei,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts"],
        set_={
            "tx_count": stmt.excluded.tx_count,
            "gas_price_gwei": stmt.excluded.gas_price_gwei,
            "base_fee": stmt.excluded.base_fee,
        },
    )
    session.execute(stmt)
    session.commit()


class AlchemyClient:
    def __init__(self, ws) -> None:
        self._ws = ws
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._subs: dict[str, asyncio.Queue] = {}

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def call(self, method: str, params: list, timeout: float = RPC_CALL_TIMEOUT_S) -> dict:
        rid = self._next_id()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        try:
            await self._ws.send(json.dumps(payload))
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(rid, None)

    async def subscribe(self, params: list) -> asyncio.Queue:
        res = await self.call("eth_subscribe", params)
        sub_id = res["result"]
        q: asyncio.Queue = asyncio.Queue()
        self._subs[sub_id] = q
        return q

    def _abort(self, exc: BaseException) -> None:
        """Wake every awaiting caller and subscription consumer so a dead
        WS doesn't leave coroutines parked on futures or empty queues."""
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()
        for q in self._subs.values():
            try:
                q.put_nowait(None)  # consumers treat None as "stream ended"
            except asyncio.QueueFull:
                pass
        self._subs.clear()

    async def pump(self) -> None:
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                if "id" in msg and msg["id"] in self._pending:
                    self._pending.pop(msg["id"]).set_result(msg)
                elif msg.get("method") == "eth_subscription":
                    sub_id = msg["params"]["subscription"]
                    q = self._subs.get(sub_id)
                    if q is not None:
                        await q.put(msg["params"]["result"])
        finally:
            self._abort(ConnectionError("ws pump exited"))


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

    try:
        net_point = extract_network_activity(block)
        with sessionmaker() as session:
            _persist_network(session, net_point)
    except Exception:
        log.exception("failed to persist network activity for block %d", block_number)

    logs_res = await client.call(
        "eth_getLogs",
        [{
            "fromBlock": hex_bn,
            "toBlock": hex_bn,
            "address": ALL_TRACKED_ADDRESSES,
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

        def eth_usd_provider() -> float | None:
            with sessionmaker() as session:
                return _latest_eth_usd(session)

        try:
            heads = await client.subscribe(["newHeads"])
            log.info("subscribed to newHeads")
            mempool_task = asyncio.create_task(
                run_mempool_loop(client, sessionmaker, eth_usd_provider, thresholds)
            )
            try:
                while True:
                    head = await next_head(heads, HEAD_STALL_TIMEOUT_S)
                    if head is None:
                        log.warning(
                            "head stream stalled or ended — reconnecting (timeout=%.0fs)",
                            HEAD_STALL_TIMEOUT_S,
                        )
                        return  # outer main() loop recreates the WS
                    bn = int(head["number"], 16)
                    try:
                        await _process_block(client, bn, sessionmaker, thresholds)
                    except (asyncio.TimeoutError, ConnectionError):
                        # WS went silent or died mid-block; bail out so the
                        # outer loop reconnects rather than spinning on a
                        # dead client.
                        log.warning("block %d processing aborted (ws unreachable)", bn)
                        return
                    except Exception:
                        log.exception("block %d processing failed", bn)
            finally:
                mempool_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await mempool_task
        finally:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pump_task


async def main() -> None:
    settings = get_settings()
    ws_url = settings.effective_ws_url
    if not ws_url:
        log.warning("no eth ws url configured (set ALCHEMY_WS_URL or ALCHEMY_API_KEY) — realtime listener idling")
        while True:
            await asyncio.sleep(3600)

    sessionmaker = get_sessionmaker()
    thresholds = (settings.whale_eth_threshold, settings.whale_stable_threshold_usd)
    log.info("starting realtime listener thresholds eth>=%s stable_usd>=%s at %s using %s",
             thresholds[0], thresholds[1], datetime.now(UTC).isoformat(),
             "self-hosted node" if settings.alchemy_ws_url else "alchemy")

    while True:
        try:
            await run_once(ws_url, sessionmaker, thresholds)
        except Exception:
            log.exception("listener crashed, reconnecting in %.0fs", RECONNECT_DELAY_S)
            await asyncio.sleep(RECONNECT_DELAY_S)


if __name__ == "__main__":
    asyncio.run(main())
