"""Tiny async JSON-RPC HTTP client for the wallet-profile balance lookups.

Used only here, not in the realtime listener (which has its own WS-based
client). Kept minimal on purpose — adding web3.py would pull in heavy deps
when all we need is eth_blockNumber, eth_getBlockByNumber, and
eth_getBalance.
"""
from __future__ import annotations

import asyncio
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


async def gather_balances(
    client: EthRpcClient,
    address: str,
    blocks: list[int],
    *,
    batch_size: int = 5,
) -> list[int]:
    """Fetch balances at each given block, capped to `batch_size` in flight.

    The cap protects a self-hosted node from a 30-call thundering herd while
    still being far faster than serial calls. Order matches `blocks`.
    """
    results: list[int] = [0] * len(blocks)
    sem = asyncio.Semaphore(batch_size)

    async def fetch_one(i: int, b: int) -> None:
        async with sem:
            results[i] = await client.get_balance(address, b)

    await asyncio.gather(*[fetch_one(i, b) for i, b in enumerate(blocks)])
    return results
