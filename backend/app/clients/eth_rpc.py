"""Tiny async JSON-RPC HTTP client for the wallet-profile balance lookups.

Used only here, not in the realtime listener (which has its own WS-based
client). Kept minimal on purpose — adding web3.py would pull in heavy deps
when all we need is eth_blockNumber, eth_getBlockByNumber, and
eth_getBalance.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx


class RpcError(RuntimeError):
    pass


class EthRpcClient:
    def __init__(self, http: httpx.AsyncClient, url: str) -> None:
        self._http = http
        self._url = url
        self._id = 0

    async def call(self, method: str, params: list[Any]) -> Any:
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params,
        }
        r = await self._http.post(self._url, json=payload, timeout=15.0)
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RpcError(f"{method}: {body['error']}")
        return body["result"]

    async def block_number(self) -> int:
        result = await self.call("eth_blockNumber", [])
        return int(result, 16)

    async def get_balance(self, address: str, block: int | str = "latest") -> int:
        block_param = block if isinstance(block, str) else hex(block)
        result = await self.call("eth_getBalance", [address, block_param])
        return int(result, 16)

    async def get_block_timestamp(self, block: int) -> int:
        result = await self.call("eth_getBlockByNumber", [hex(block), False])
        if not result:
            raise RpcError(f"block {block} not found")
        return int(result["timestamp"], 16)

    async def batch_eth_call(
        self, calls: list[tuple[str, str]], block: int | str = "latest"
    ) -> list[str | None]:
        """Issue N eth_calls in a single JSON-RPC batch POST.

        Each entry in `calls` is `(to_address, data_hex)`. Returns the raw
        hex result per call (in input order), or None for per-call errors.
        Used by the token-holdings lookup to fetch ~25 ERC-20 `balanceOf`
        values in one round-trip.
        """
        if not calls:
            return []
        block_param = block if isinstance(block, str) else hex(block)
        first_id = self._id + 1
        payload = []
        for to, data in calls:
            self._id += 1
            payload.append(
                {
                    "jsonrpc": "2.0",
                    "id": self._id,
                    "method": "eth_call",
                    "params": [{"to": to, "data": data}, block_param],
                }
            )
        r = await self._http.post(self._url, json=payload, timeout=15.0)
        r.raise_for_status()
        body = r.json()
        if isinstance(body, dict):
            raise RpcError(f"batch_eth_call: expected array, got {body!r}")
        by_id = {item["id"]: item for item in body}
        out: list[str | None] = []
        for i in range(len(calls)):
            item = by_id.get(first_id + i)
            if item is None or "error" in item:
                out.append(None)
            else:
                out.append(item.get("result"))
        return out


async def gather_balances(
    client: EthRpcClient,
    address: str,
    blocks: list[int],
    *,
    batch_size: int = 5,
) -> list[int | None]:
    """Fetch balances at each given block, capped to `batch_size` in flight.

    Returns a list parallel to `blocks` where each entry is either the
    balance in wei (success) or None (per-block failure — most commonly
    'historical state ... is not available' on snap-sync nodes that have
    pruned the trie at older blocks). Caller skips None entries rather
    than aborting the whole profile.

    The cap protects a self-hosted node from a 30-call thundering herd
    while still being far faster than serial calls. Order matches `blocks`.
    """
    results: list[int | None] = [None] * len(blocks)
    sem = asyncio.Semaphore(batch_size)

    async def fetch_one(i: int, b: int) -> None:
        async with sem:
            try:
                results[i] = await client.get_balance(address, b)
            except (RpcError, httpx.HTTPError, OSError) as exc:
                # Snap-sync nodes prune older trie state; archive nodes
                # may rate-limit. Either way, skip this block rather than
                # poisoning the whole batch.
                logging.getLogger(__name__).debug(
                    "get_balance(%s, %d) failed: %s -- skipping", address, b, exc
                )
                results[i] = None

    await asyncio.gather(*[fetch_one(i, b) for i, b in enumerate(blocks)])
    return results
