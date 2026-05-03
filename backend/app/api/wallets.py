"""Wallet profile API.

GET /api/wallets/{address}/profile

Aggregates four already-indexed sources into one round-trip response so
the frontend drawer can render the whole view from a single fetch:
* historical ETH balance (eth_getBalance + Postgres cache)
* recent whale transfers involving the address
* top counterparties (30d) from `transfers`
* daily net USD flow (7d) from `transfers`

Unlike the cluster endpoint this is computed mostly from local Postgres
state, with one HTTP-RPC burst on the first lookup of a never-seen
address. Subsequent lookups read entirely from cache except for one
"latest balance" call.
"""
from __future__ import annotations

import re
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import WalletProfile
from app.clients.eth_rpc import EthRpcClient
from app.core.config import get_settings
from app.core.db import get_session
from app.core.models import PriceCandle
from app.services.wallet_profile import build_profile_async

router = APIRouter(prefix="/wallets", tags=["wallets"])

_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _validate(address: str) -> str:
    if not _ADDR_RE.match(address):
        raise HTTPException(status_code=400, detail="malformed_address")
    return address.lower()


def _latest_eth_price(session: Session) -> float | None:
    row = session.execute(
        select(PriceCandle.close)
        .where(PriceCandle.symbol == "ETHUSDT", PriceCandle.timeframe == "1h")
        .order_by(PriceCandle.ts.desc())
        .limit(1)
    ).scalar_one_or_none()
    return float(row) if row is not None else None


@router.get("/{address}/profile", response_model=WalletProfile)
async def get_wallet_profile(
    address: str,
    session: Annotated[Session, Depends(get_session)],
) -> WalletProfile:
    addr = _validate(address)
    settings = get_settings()
    eth_price = _latest_eth_price(session)

    rpc_url = settings.effective_http_url
    if not rpc_url:
        # No RPC configured — return profile without balance history or
        # token holdings. The frontend renders the rest (cluster,
        # counterparties, activity).
        return await build_profile_async(
            session, None, None, addr, eth_price, settings.coingecko_api_key
        )

    # Tight timeout (was 20s). The drawer is interactive — if the configured
    # RPC node is unreachable (dev .env points at a host with nothing listening,
    # or a self-hosted node is briefly down), we want to fail fast and degrade
    # to "balance unavailable" rather than blocking the user for 20s+.
    # 4s comfortably covers a healthy round-trip (~50-200ms typical) plus
    # headroom for cold archive queries.
    async with httpx.AsyncClient(timeout=4.0) as http:
        rpc = EthRpcClient(http, rpc_url)
        return await build_profile_async(
            session, rpc, http, addr, eth_price, settings.coingecko_api_key
        )
