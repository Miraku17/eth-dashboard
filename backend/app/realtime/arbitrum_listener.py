"""Arbitrum WebSocket listener — GMX V2 perp events.

Sibling to the mainnet `app.realtime.listener`; dedicated process so an
Arbitrum endpoint hiccup or GMX-decoder bug can't disrupt mainnet
processing. Same WS-client / reconnect pattern (cribbed from listener.py).

Subscribe pattern:
- `eth_subscribe newHeads` — block clock so we know when to fetch logs.
- Per block, `eth_getLogs` filtered to the GMX V2 EventEmitter address
  with topics[1] in {keccak("PositionIncrease"), keccak("PositionDecrease")}.
  This is far cheaper than a `logs` subscription (Alchemy rate-limits the
  latter) and lets us keep our own block-level batching cadence.
- For each decoded event, look up the originating EOA via the tx receipt
  (Redis-cached). The `msgSender` in the EventLogData is GMX's router, not
  the user — without this we'd tag every position to the same proxy address.

Run as `python -m app.realtime.arbitrum_listener` from the
`arbitrum_realtime` docker-compose service.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime

import httpx
import redis as redis_lib
import websockets
from redis.asyncio import Redis as AsyncRedis  # async client, separate from the sync redis_lib used by TxFromResolver

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.models import PerpWatchlist
from app.realtime.gmx_v2_decoder import (
    GMX_V2_EVENT_EMITTER,
    decode as decode_gmx,
)
from app.realtime.gmx_v2_decoder import (
    _TOPIC_POSITION_DECREASE,
    _TOPIC_POSITION_INCREASE,
)
from app.realtime.perp_watchlist_cache import PerpWatchlistCache
from app.realtime.perp_writer import PerpWriter, make_row
from app.services.perp_watch_dispatch import dispatch_perp_watch
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("arbitrum_realtime")

RECONNECT_DELAY_S = 5.0
HEAD_STALL_TIMEOUT_S = 60.0
RPC_CALL_TIMEOUT_S = 30.0
TX_FROM_CACHE_TTL_S = 3600  # 1h — receipts are immutable per tx_hash


class ArbitrumClient:
    """JSON-RPC-over-WS client. Same shape as the mainnet AlchemyClient
    in listener.py; kept local so a future divergence doesn't accidentally
    reach across listeners."""

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
        try:
            await self._ws.send(json.dumps({
                "jsonrpc": "2.0", "id": rid, "method": method, "params": params,
            }))
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
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()
        for q in self._subs.values():
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(None)
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


class TxFromResolver:
    """Resolve `tx.from` (the originating EOA) for an Arbitrum tx, with a
    Redis cache so the same tx isn't fetched twice across listener runs.

    Uses HTTP JSON-RPC rather than the WS client so a slow receipt fetch
    doesn't block the WS pump.
    """

    def __init__(self, http_url: str, redis_url: str) -> None:
        self._http_url = http_url
        self._http = httpx.AsyncClient(timeout=20.0)
        self._redis = redis_lib.from_url(redis_url, decode_responses=True)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def resolve(self, tx_hash: str) -> str | None:
        key = f"arb_tx_from:{tx_hash.lower()}"
        cached = self._redis.get(key)
        if cached:
            return cached
        try:
            resp = await self._http.post(
                self._http_url,
                json={
                    "jsonrpc": "2.0", "id": 1,
                    "method": "eth_getTransactionByHash",
                    "params": [tx_hash],
                },
            )
            data = resp.json()
        except Exception:
            log.exception("eth_getTransactionByHash failed for %s", tx_hash)
            return None
        result = (data or {}).get("result") or {}
        from_addr = result.get("from")
        if from_addr:
            self._redis.set(key, from_addr.lower(), ex=TX_FROM_CACHE_TTL_S)
            return from_addr.lower()
        return None


async def next_head(queue: asyncio.Queue, timeout: float) -> dict | None:
    try:
        return await asyncio.wait_for(queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None


WATCHED_EVENT_KINDS = {"open", "increase", "close", "decrease", "liquidation"}


async def _maybe_dispatch_perp_alerts(
    rows: list[dict],
    *,
    cache: PerpWatchlistCache,
    http: httpx.AsyncClient,
    sessionmaker,
) -> None:
    """Dispatch a Telegram alert for each row whose account is on the
    watchlist and whose size clears the per-watch min-notional floor."""
    for row in rows:
        if row.get("event_kind") not in WATCHED_EVENT_KINDS:
            continue
        account = row.get("account") or ""
        floor = await cache.lookup(account)
        if floor is None:
            continue
        size_usd = row.get("size_usd")
        if size_usd is None or size_usd < floor:
            continue
        with sessionmaker() as session:
            watch = session.execute(
                select(PerpWatchlist).where(PerpWatchlist.wallet == account.lower())
            ).scalar_one_or_none()
        if watch is None:
            # Cache was stale — wallet got removed since lookup. Skip.
            continue
        try:
            await dispatch_perp_watch(http=http, event=row, watch=watch)
        except Exception:
            log.exception("dispatch_perp_watch failed account=%s tx=%s", account, row.get("tx_hash"))


def _parse_hex(h: str | int | None) -> int:
    if h is None:
        return 0
    if isinstance(h, int):
        return h
    return int(h, 16)


async def _process_block(
    client: ArbitrumClient,
    resolver: TxFromResolver,
    writer: PerpWriter,
    block_number: int,
    *,
    perp_watch_cache: PerpWatchlistCache | None = None,
    perp_alert_http: httpx.AsyncClient | None = None,
    sessionmaker=None,
) -> None:
    hex_bn = hex(block_number)
    block_res = await client.call("eth_getBlockByNumber", [hex_bn, False])
    block = block_res.get("result")
    if not block:
        return
    ts = datetime.fromtimestamp(_parse_hex(block.get("timestamp")), tz=UTC)

    logs_res = await client.call(
        "eth_getLogs",
        [{
            "fromBlock": hex_bn,
            "toBlock": hex_bn,
            "address": GMX_V2_EVENT_EMITTER,
            # OR-filter on topics[1] — Arbitrum getLogs supports an array
            # of values per topic position, so we can fetch both event
            # types in a single call.
            "topics": [None, [_TOPIC_POSITION_INCREASE, _TOPIC_POSITION_DECREASE]],
        }],
    )
    raw_logs = logs_res.get("result") or []
    if not raw_logs:
        return

    # Decode every matching log; group by tx hash so receipt lookups dedupe.
    decoded = []
    tx_hashes_needed: set[str] = set()
    for lg in raw_logs:
        ev = decode_gmx(lg)
        if ev is None:
            continue
        txh = (lg.get("transactionHash") or "").lower()
        log_idx = _parse_hex(lg.get("logIndex"))
        decoded.append((ev, txh, log_idx))
        tx_hashes_needed.add(txh)

    if not decoded:
        return

    # Resolve EOAs for every distinct tx in this block in parallel.
    eoa_tasks = {h: asyncio.create_task(resolver.resolve(h)) for h in tx_hashes_needed}
    await asyncio.gather(*eoa_tasks.values(), return_exceptions=True)
    eoa_by_tx: dict[str, str | None] = {}
    for h, task in eoa_tasks.items():
        try:
            eoa_by_tx[h] = task.result()
        except Exception:
            eoa_by_tx[h] = None

    rows: list[dict] = []
    for ev, txh, log_idx in decoded:
        eoa = eoa_by_tx.get(txh)
        # Override the decoder's account (which is from topics[2]) with the
        # tx-receipt EOA when we have it. Falls back to the decoded account
        # if the receipt lookup failed.
        if eoa:
            ev_with_eoa = ev.__class__(
                **{**ev.__dict__, "account": eoa},
            )
        else:
            ev_with_eoa = ev
        rows.append(make_row(ev_with_eoa, ts=ts, tx_hash=txh, log_index=log_idx))

    if rows:
        inserted = writer.write(rows)
        log.info(
            "block=%d gmx_events=%d persisted=%d",
            block_number, len(rows), inserted,
        )
        if perp_watch_cache is not None and perp_alert_http is not None and sessionmaker is not None:
            await _maybe_dispatch_perp_alerts(
                rows,
                cache=perp_watch_cache,
                http=perp_alert_http,
                sessionmaker=sessionmaker,
            )


async def run_once(ws_url: str, http_url: str, redis_url: str, sessionmaker) -> None:
    writer = PerpWriter(sessionmaker)
    resolver = TxFromResolver(http_url, redis_url)
    perp_watch_cache: PerpWatchlistCache | None = None
    perp_alert_http: httpx.AsyncClient | None = None
    try:
        async_redis = AsyncRedis.from_url(redis_url, decode_responses=True)
        perp_watch_cache = PerpWatchlistCache(async_redis)
        await perp_watch_cache.start()
        perp_alert_http = httpx.AsyncClient(timeout=10.0)
    except Exception:
        log.exception("perp_watch_cache: failed to initialize; alerts disabled this run")
        perp_watch_cache = None
    try:
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
            client = ArbitrumClient(ws)
            pump_task = asyncio.create_task(client.pump())
            try:
                heads = await client.subscribe(["newHeads"])
                log.info("subscribed to arbitrum newHeads")
                while True:
                    head = await next_head(heads, HEAD_STALL_TIMEOUT_S)
                    if head is None:
                        log.warning(
                            "arbitrum head stream stalled — reconnecting (timeout=%.0fs)",
                            HEAD_STALL_TIMEOUT_S,
                        )
                        return
                    bn = int(head["number"], 16)
                    try:
                        await _process_block(
                            client, resolver, writer, bn,
                            perp_watch_cache=perp_watch_cache,
                            perp_alert_http=perp_alert_http,
                            sessionmaker=sessionmaker,
                        )
                    except (asyncio.TimeoutError, ConnectionError):
                        log.warning("arbitrum block %d processing aborted (ws unreachable)", bn)
                        return
                    except Exception:
                        log.exception("arbitrum block %d processing failed", bn)
            finally:
                pump_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pump_task
    finally:
        await resolver.aclose()
        if perp_alert_http is not None:
            await perp_alert_http.aclose()


async def main() -> None:
    settings = get_settings()
    ws_url = settings.effective_arbitrum_ws_url
    http_url = settings.effective_arbitrum_http_url
    redis_url = settings.redis_url
    sessionmaker = get_sessionmaker()

    if not ws_url or not http_url:
        log.warning(
            "arbitrum endpoints not configured — set ARBITRUM_WS_URL + "
            "ARBITRUM_HTTP_URL (or ALCHEMY_API_KEY for default Alchemy "
            "fallback). Listener idling.",
        )
        while True:
            await asyncio.sleep(3600)

    log.info(
        "starting arbitrum listener at %s using %s",
        datetime.now(UTC).isoformat(),
        "self-hosted node" if settings.arbitrum_ws_url else "alchemy",
    )
    while True:
        try:
            await run_once(ws_url, http_url, redis_url, sessionmaker)
        except Exception:
            log.exception("arbitrum listener crashed, reconnecting in %.0fs", RECONNECT_DELAY_S)
            await asyncio.sleep(RECONNECT_DELAY_S)


if __name__ == "__main__":
    asyncio.run(main())
