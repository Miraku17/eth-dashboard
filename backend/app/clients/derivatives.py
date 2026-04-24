"""Exchange clients for ETH perpetual derivatives data (OI + funding + mark).

Each exchange returns a single `DerivativesSnapshot` per call — no historical
backfill for v2 Phase A. We call every hour from a cron and accumulate the
time series in Postgres.

Public endpoints, no auth, no API key required.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

BINANCE_FAPI = "https://fapi.binance.com"
BYBIT_API = "https://api.bybit.com"
OKX_API = "https://www.okx.com"
DERIBIT_API = "https://www.deribit.com"


@dataclass(frozen=True)
class DerivSnap:
    exchange: str
    symbol: str
    ts: datetime
    oi_usd: float | None
    funding_rate: float | None
    mark_price: float | None


async def fetch_binance(http: httpx.AsyncClient) -> DerivSnap:
    # OI returns contracts (base asset amount for COIN-M, quote for USDT-M).
    # ETHUSDT is USDT-margined → openInterest is in ETH, we multiply by mark.
    oi_res = await http.get(f"{BINANCE_FAPI}/fapi/v1/openInterest", params={"symbol": "ETHUSDT"}, timeout=10)
    oi_res.raise_for_status()
    oi = oi_res.json()
    prem_res = await http.get(f"{BINANCE_FAPI}/fapi/v1/premiumIndex", params={"symbol": "ETHUSDT"}, timeout=10)
    prem_res.raise_for_status()
    prem = prem_res.json()
    mark = float(prem["markPrice"])
    return DerivSnap(
        exchange="binance",
        symbol="ETHUSDT",
        ts=datetime.now(UTC),
        oi_usd=float(oi["openInterest"]) * mark,
        funding_rate=float(prem["lastFundingRate"]),
        mark_price=mark,
    )


async def fetch_bybit(http: httpx.AsyncClient) -> DerivSnap:
    r = await http.get(
        f"{BYBIT_API}/v5/market/tickers",
        params={"category": "linear", "symbol": "ETHUSDT"},
        timeout=10,
    )
    r.raise_for_status()
    body = r.json()
    row = body["result"]["list"][0]
    mark = float(row["markPrice"])
    # Bybit: `openInterest` is in contracts (= ETH for linear); convert to USD.
    return DerivSnap(
        exchange="bybit",
        symbol="ETHUSDT",
        ts=datetime.now(UTC),
        oi_usd=float(row["openInterest"]) * mark,
        funding_rate=float(row["fundingRate"]),
        mark_price=mark,
    )


async def fetch_okx(http: httpx.AsyncClient) -> DerivSnap:
    oi_res = await http.get(
        f"{OKX_API}/api/v5/public/open-interest",
        params={"instId": "ETH-USDT-SWAP"},
        timeout=10,
    )
    oi_res.raise_for_status()
    oi_row = oi_res.json()["data"][0]

    fr_res = await http.get(
        f"{OKX_API}/api/v5/public/funding-rate",
        params={"instId": "ETH-USDT-SWAP"},
        timeout=10,
    )
    fr_res.raise_for_status()
    fr_row = fr_res.json()["data"][0]

    mark_res = await http.get(
        f"{OKX_API}/api/v5/market/ticker",
        params={"instId": "ETH-USDT-SWAP"},
        timeout=10,
    )
    mark_res.raise_for_status()
    mark = float(mark_res.json()["data"][0]["last"])

    # OKX `oiCcy` is OI in base currency (ETH); multiply to get USD.
    oi_eth = float(oi_row.get("oiCcy") or oi_row.get("oi") or 0)
    return DerivSnap(
        exchange="okx",
        symbol="ETH-USDT-SWAP",
        ts=datetime.now(UTC),
        oi_usd=oi_eth * mark if oi_eth else None,
        funding_rate=float(fr_row["fundingRate"]),
        mark_price=mark,
    )


async def fetch_deribit(http: httpx.AsyncClient) -> DerivSnap:
    # Deribit quotes in USD for the ETH-PERPETUAL contract.
    r = await http.get(
        f"{DERIBIT_API}/api/v2/public/ticker",
        params={"instrument_name": "ETH-PERPETUAL"},
        timeout=10,
    )
    r.raise_for_status()
    result = r.json()["result"]
    # `open_interest` on Deribit is in USD for USD-margined perps.
    return DerivSnap(
        exchange="deribit",
        symbol="ETH-PERPETUAL",
        ts=datetime.now(UTC),
        oi_usd=float(result["open_interest"]),
        # `current_funding` = current 8h-annualised funding; `funding_8h` is the
        # past-8h realised rate. We store the latter for apples-to-apples
        # comparison with Binance/Bybit/OKX's `lastFundingRate`.
        funding_rate=float(result.get("funding_8h") or 0),
        mark_price=float(result["mark_price"]),
    )


FETCHERS = {
    "binance": fetch_binance,
    "bybit": fetch_bybit,
    "okx": fetch_okx,
    "deribit": fetch_deribit,
}
