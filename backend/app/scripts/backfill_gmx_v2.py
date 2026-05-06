"""Backfill historical GMX V2 perp events into `onchain_perp_event`.

The realtime listener is forward-only — it processes blocks as they arrive
and ignores history. This one-shot script pages through `eth_getLogs` on
Arbitrum mainnet for the GMX V2 EventEmitter (`0xC8ee91A...`) over a
configurable window, decodes each PositionIncrease / PositionDecrease,
resolves the originating EOA per tx, and bulk-upserts.

Idempotent: `ON CONFLICT (tx_hash, log_index) DO NOTHING` means re-running
the same window is a safe no-op for already-imported events. The Redis
cache in TxFromResolver also makes re-runs cheap on the receipt side.

Usage:
    python -m app.scripts.backfill_gmx_v2 --days 30
    python -m app.scripts.backfill_gmx_v2 --days 7 --chunk-blocks 5000
    python -m app.scripts.backfill_gmx_v2 --from-block 270000000 --to-block 270100000

Env required:
    ALCHEMY_API_KEY  (or explicit ARBITRUM_HTTP_URL)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import UTC, datetime

import httpx

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.realtime.arbitrum_listener import TxFromResolver
from app.realtime.gmx_v2_decoder import (
    GMX_V2_EVENT_EMITTER,
    _TOPIC_POSITION_DECREASE,
    _TOPIC_POSITION_INCREASE,
    decode as decode_gmx,
)
from app.realtime.perp_writer import PerpWriter, make_row

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("backfill_gmx_v2")

# Arbitrum produces ~4 blocks/sec (≈0.25s block time). Used only to
# estimate a start block from a `--days` argument; exact timing doesn't
# matter — we bias slightly older to cover any drift.
ARBITRUM_BLOCKS_PER_SEC = 4

# Alchemy's eth_getLogs caps the response at 10k logs OR 10k blocks per
# request, whichever hits first. 5k blocks is a safe default that stays
# well under both for GMX-V2-only filtered queries.
DEFAULT_CHUNK_BLOCKS = 5_000

# Bound concurrent receipt fetches so we don't trip Alchemy's CU/sec rate
# limit during the resolve phase. 20 is comfortably below the 300 CU/sec
# free-tier ceiling once you account for the cost per eth_getTxByHash.
RESOLVE_CONCURRENCY = 20


async def _get_latest_block(http_url: str) -> int:
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(http_url, json={
            "jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": [],
        })
        r.raise_for_status()
        return int(r.json()["result"], 16)


async def _get_logs(
    http: httpx.AsyncClient, http_url: str, *, from_block: int, to_block: int,
) -> list[dict]:
    r = await http.post(http_url, json={
        "jsonrpc": "2.0", "id": 1, "method": "eth_getLogs",
        "params": [{
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": GMX_V2_EVENT_EMITTER,
            "topics": [None, [_TOPIC_POSITION_INCREASE, _TOPIC_POSITION_DECREASE]],
        }],
    })
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"eth_getLogs error: {body['error']}")
    return body.get("result") or []


async def _get_block_timestamps(
    http: httpx.AsyncClient, http_url: str, block_numbers: set[int],
) -> dict[int, datetime]:
    """Batched eth_getBlockByNumber (transactions=False) for a set of block
    numbers. Cheaper than per-event lookups since GMX events cluster in
    the same block."""
    if not block_numbers:
        return {}
    payload = [
        {"jsonrpc": "2.0", "id": i, "method": "eth_getBlockByNumber",
         "params": [hex(bn), False]}
        for i, bn in enumerate(block_numbers)
    ]
    r = await http.post(http_url, json=payload)
    r.raise_for_status()
    out: dict[int, datetime] = {}
    blocks_by_id = {p["id"]: p["params"][0] for p in payload}
    for entry in r.json():
        block_hex = blocks_by_id[entry["id"]]
        result = entry.get("result") or {}
        ts_hex = result.get("timestamp")
        if not ts_hex:
            continue
        out[int(block_hex, 16)] = datetime.fromtimestamp(int(ts_hex, 16), tz=UTC)
    return out


async def _resolve_eoas(
    resolver: TxFromResolver, tx_hashes: set[str],
) -> dict[str, str | None]:
    """Resolve the originating EOA for each tx_hash, bounded concurrency."""
    sem = asyncio.Semaphore(RESOLVE_CONCURRENCY)

    async def _one(h: str) -> tuple[str, str | None]:
        async with sem:
            return h, await resolver.resolve(h)

    pairs = await asyncio.gather(*(_one(h) for h in tx_hashes), return_exceptions=False)
    return dict(pairs)


async def _process_chunk(
    http: httpx.AsyncClient, http_url: str, resolver: TxFromResolver,
    writer: PerpWriter, from_block: int, to_block: int,
) -> tuple[int, int]:
    """Returns (decoded_count, persisted_count)."""
    raw_logs = await _get_logs(http, http_url, from_block=from_block, to_block=to_block)
    if not raw_logs:
        return 0, 0

    # Decode + collect what we need to look up (block timestamps + tx EOAs).
    decoded: list[tuple] = []  # (ev, tx_hash, log_index, block_number)
    tx_hashes: set[str] = set()
    block_numbers: set[int] = set()
    for lg in raw_logs:
        ev = decode_gmx(lg)
        if ev is None:
            continue
        txh = (lg.get("transactionHash") or "").lower()
        log_idx = int(lg.get("logIndex") or "0x0", 16)
        bn = int(lg.get("blockNumber") or "0x0", 16)
        decoded.append((ev, txh, log_idx, bn))
        tx_hashes.add(txh)
        block_numbers.add(bn)

    if not decoded:
        return 0, 0

    # Parallel: block timestamps (one batched RPC) + EOA resolution
    # (concurrent per-tx with a semaphore).
    ts_by_block, eoa_by_tx = await asyncio.gather(
        _get_block_timestamps(http, http_url, block_numbers),
        _resolve_eoas(resolver, tx_hashes),
    )

    rows: list[dict] = []
    for ev, txh, log_idx, bn in decoded:
        ts = ts_by_block.get(bn)
        if ts is None:
            continue  # missing timestamp → skip rather than insert garbage
        eoa = eoa_by_tx.get(txh)
        if eoa:
            ev = ev.__class__(**{**ev.__dict__, "account": eoa})
        rows.append(make_row(ev, ts=ts, tx_hash=txh, log_index=log_idx))

    persisted = writer.write(rows) if rows else 0
    return len(decoded), persisted


async def run(
    *, from_block: int, to_block: int, chunk_blocks: int,
    http_url: str, redis_url: str, sessionmaker,
) -> None:
    if from_block > to_block:
        raise SystemExit(f"from_block ({from_block}) > to_block ({to_block})")
    total_blocks = to_block - from_block + 1
    log.info(
        "backfill range: %d → %d (%d blocks, %d-block chunks)",
        from_block, to_block, total_blocks, chunk_blocks,
    )

    writer = PerpWriter(sessionmaker)
    resolver = TxFromResolver(http_url, redis_url)
    started = time.time()
    grand_decoded = 0
    grand_persisted = 0
    chunks_done = 0
    chunks_total = (total_blocks + chunk_blocks - 1) // chunk_blocks

    try:
        async with httpx.AsyncClient(timeout=60.0) as http:
            cur = from_block
            while cur <= to_block:
                chunk_end = min(cur + chunk_blocks - 1, to_block)
                t0 = time.time()
                try:
                    decoded, persisted = await _process_chunk(
                        http, http_url, resolver, writer, cur, chunk_end,
                    )
                except Exception:
                    log.exception(
                        "chunk %d-%d failed; continuing with next chunk", cur, chunk_end,
                    )
                    decoded, persisted = 0, 0
                grand_decoded += decoded
                grand_persisted += persisted
                chunks_done += 1
                elapsed = time.time() - t0
                pct = chunks_done * 100 // chunks_total
                log.info(
                    "[%3d%%] %d-%d  decoded=%d persisted=%d  (%.1fs)  total=%d/%d",
                    pct, cur, chunk_end, decoded, persisted, elapsed,
                    grand_persisted, grand_decoded,
                )
                cur = chunk_end + 1
    finally:
        await resolver.aclose()

    log.info(
        "backfill complete in %.1fs — decoded=%d persisted=%d",
        time.time() - started, grand_decoded, grand_persisted,
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="backfill_gmx_v2",
        description="Backfill GMX V2 perp events into onchain_perp_event.",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--days", type=int, help="backfill the last N days (estimated block range)")
    g.add_argument("--from-block", type=int, help="explicit start block (use with --to-block)")
    p.add_argument("--to-block", type=int, help="explicit end block; defaults to latest")
    p.add_argument(
        "--chunk-blocks", type=int, default=DEFAULT_CHUNK_BLOCKS,
        help=f"blocks per eth_getLogs call (default {DEFAULT_CHUNK_BLOCKS})",
    )
    return p.parse_args()


async def amain() -> int:
    args = _parse_args()
    settings = get_settings()
    http_url = settings.effective_arbitrum_http_url
    if not http_url:
        print(
            "no arbitrum HTTP endpoint — set ARBITRUM_HTTP_URL or ALCHEMY_API_KEY",
            file=sys.stderr,
        )
        return 1

    latest = await _get_latest_block(http_url)
    if args.days is not None:
        from_block = max(1, latest - args.days * 86400 * ARBITRUM_BLOCKS_PER_SEC)
        to_block = latest
    else:
        from_block = args.from_block
        to_block = args.to_block if args.to_block is not None else latest

    sessionmaker = get_sessionmaker()
    await run(
        from_block=from_block,
        to_block=to_block,
        chunk_blocks=args.chunk_blocks,
        http_url=http_url,
        redis_url=settings.redis_url,
        sessionmaker=sessionmaker,
    )
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    raise SystemExit(main())
