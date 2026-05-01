"""ERC-20 holdings lookup for the wallet profile drawer.

Strategy:
* Curated list of ~25 mainnet tokens that cover ~90% of what crypto-native
  wallets actually hold by USD value (stables, majors, blue-chip DeFi, top
  L2 governance, top memes, LSDs).
* All `balanceOf(address)` calls go out as a single JSON-RPC batch POST,
  so 25 reads = 1 RPC round trip.
* USD pricing via CoinGecko `simple/token_price/ethereum`, cached 5 min in
  Redis. If the call fails we still surface raw token amounts.
* Per-address result cached in Redis 60s so repeated drawer-opens don't
  hit the node.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.api.schemas import TokenHolding
from app.clients.eth_rpc import EthRpcClient, RpcError
from app.core.cache import cached_json_get, cached_json_set

log = logging.getLogger(__name__)

# `balanceOf(address)` selector = first 4 bytes of keccak256("balanceOf(address)").
_BALANCE_OF_SELECTOR = "0x70a08231"

# Static curated list. Address must be lowercase to match CoinGecko response keys.
TOKEN_LIST: list[dict[str, Any]] = [
    # Stables
    {"address": "0xdac17f958d2ee523a2206206994597c13d831ec7", "symbol": "USDT", "decimals": 6},
    {"address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "symbol": "USDC", "decimals": 6},
    {"address": "0x6b175474e89094c44da98b954eedeac495271d0f", "symbol": "DAI", "decimals": 18},
    {"address": "0x853d955acef822db058eb8505911ed77f175b99e", "symbol": "FRAX", "decimals": 18},
    # Majors
    {"address": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "symbol": "WETH", "decimals": 18},
    {"address": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", "symbol": "WBTC", "decimals": 8},
    # Liquid-staking derivatives
    {"address": "0xae7ab96520de3a18e5e111b5eaab095312d7fe84", "symbol": "stETH", "decimals": 18},
    {"address": "0xae78736cd615f374d3085123a210448e74fc6393", "symbol": "rETH", "decimals": 18},
    # DeFi blue-chips
    {"address": "0x514910771af9ca656af840dff83e8264ecf986ca", "symbol": "LINK", "decimals": 18},
    {"address": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984", "symbol": "UNI", "decimals": 18},
    {"address": "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9", "symbol": "AAVE", "decimals": 18},
    {"address": "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2", "symbol": "MKR", "decimals": 18},
    {"address": "0x5a98fcbea516cf06857215779fd812ca3bef1b32", "symbol": "LDO", "decimals": 18},
    {"address": "0xc00e94cb662c3520282e6f5717214004a7f26888", "symbol": "COMP", "decimals": 18},
    {"address": "0xd533a949740bb3306d119cc777fa900ba034cd52", "symbol": "CRV", "decimals": 18},
    {"address": "0x4e3fbd56cd56c3e72c1403e103b45db9da5b9d2b", "symbol": "CVX", "decimals": 18},
    # Layer-2 governance / utility
    {"address": "0xb50721bcf8d664c30412cfbc6cf7a15145234ad1", "symbol": "ARB", "decimals": 18},
    {"address": "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0", "symbol": "MATIC", "decimals": 18},
    {"address": "0xc944e90c64b2c07662a292be6244bdf05cda44a7", "symbol": "GRT", "decimals": 18},
    {"address": "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72", "symbol": "ENS", "decimals": 18},
    {"address": "0x111111111117dc0aa78b770fa6a738034120c302", "symbol": "1INCH", "decimals": 18},
    # Memes (high turnover in trader wallets)
    {"address": "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce", "symbol": "SHIB", "decimals": 18},
    {"address": "0x6982508145454ce325ddbe47a25d4ec3d2311933", "symbol": "PEPE", "decimals": 18},
]
TOKENS_BY_ADDRESS: dict[str, dict[str, Any]] = {t["address"]: t for t in TOKEN_LIST}

# Redis cache keys.
_PRICE_CACHE_KEY = "token_prices:ethereum"
_PRICE_TTL_S = 300  # 5 min — token prices move slow relative to drawer-open frequency.
_HOLDINGS_TTL_S = 60  # 1 min per-address.

# Don't surface dust — anything below this in USD value is filtered out so the
# drawer doesn't render a long tail of "0.0001 of XYZ worth $0.02".
_DUST_USD_FLOOR = 1.0
_MAX_HOLDINGS_RETURNED = 8


def _encode_balance_of(address: str) -> str:
    """ABI-encode `balanceOf(address)` calldata for the given address.

    The argument is a single static `address` type, so the calldata is just
    the 4-byte selector followed by the 32-byte left-padded address.
    """
    bare = address.lower().removeprefix("0x")
    return _BALANCE_OF_SELECTOR + bare.zfill(64)


def _decode_uint256(hex_str: str | None) -> int:
    if not hex_str or hex_str == "0x":
        return 0
    return int(hex_str, 16)


async def _fetch_prices(http: httpx.AsyncClient, api_key: str) -> dict[str, float]:
    """USD price per token contract address. Cached, free-tier-safe."""
    cached = cached_json_get(_PRICE_CACHE_KEY)
    if isinstance(cached, dict):
        return {k: float(v) for k, v in cached.items()}

    addrs = ",".join(t["address"] for t in TOKEN_LIST)
    headers = {}
    if api_key:
        # CoinGecko Demo plan header (free tier with key).
        headers["x-cg-demo-api-key"] = api_key
    try:
        r = await http.get(
            "https://api.coingecko.com/api/v3/simple/token_price/ethereum",
            params={"contract_addresses": addrs, "vs_currencies": "usd"},
            headers=headers,
            timeout=10.0,
        )
        r.raise_for_status()
        body = r.json()
    except (httpx.HTTPError, OSError) as exc:
        log.warning("token price fetch failed: %s", exc)
        return {}

    prices: dict[str, float] = {}
    for addr, payload in body.items():
        usd = payload.get("usd") if isinstance(payload, dict) else None
        if isinstance(usd, (int, float)):
            prices[addr.lower()] = float(usd)
    if prices:
        cached_json_set(_PRICE_CACHE_KEY, prices, _PRICE_TTL_S)
    return prices


async def get_token_holdings(
    rpc: EthRpcClient | None,
    http: httpx.AsyncClient,
    address: str,
    coingecko_api_key: str,
) -> list[TokenHolding]:
    if rpc is None:
        return []

    address = address.lower()
    cache_key = f"token_holdings:{address}"
    cached = cached_json_get(cache_key)
    if isinstance(cached, list):
        return [TokenHolding.model_validate(h) for h in cached]

    calls = [(t["address"], _encode_balance_of(address)) for t in TOKEN_LIST]
    try:
        raw_results = await rpc.batch_eth_call(calls)
    except (RpcError, httpx.HTTPError, OSError) as exc:
        log.warning("token balance batch failed for %s: %s", address, exc)
        return []

    prices = await _fetch_prices(http, coingecko_api_key)

    holdings: list[TokenHolding] = []
    for token, raw_hex in zip(TOKEN_LIST, raw_results, strict=True):
        bal = _decode_uint256(raw_hex)
        if bal == 0:
            continue
        amount = bal / (10 ** token["decimals"])
        price = prices.get(token["address"])
        usd = amount * price if price is not None else None
        holdings.append(
            TokenHolding(
                address=token["address"],
                symbol=token["symbol"],
                amount=amount,
                price_usd=price,
                usd_value=usd,
            )
        )

    # Sort by USD desc with unpriced tokens at the bottom; keep top N above dust.
    holdings.sort(key=lambda h: (h.usd_value is None, -(h.usd_value or 0.0)))
    pruned = [
        h for h in holdings
        if (h.usd_value is None) or (h.usd_value >= _DUST_USD_FLOOR)
    ][:_MAX_HOLDINGS_RETURNED]

    cached_json_set(
        cache_key,
        [h.model_dump(mode="json") for h in pruned],
        _HOLDINGS_TTL_S,
    )
    return pruned
