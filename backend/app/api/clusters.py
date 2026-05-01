"""Wallet clustering API.

GET  /api/clusters/{address}            return cached or compute inline
POST /api/clusters/{address}/refresh    invalidate cache and recompute
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.schemas import ClusterResult
from app.clients.etherscan import (
    ETHERSCAN_BASE_URL,
    EtherscanClient,
    EtherscanRateLimited,
    EtherscanUnavailable,
)
from app.core.config import get_settings
from app.core.db import get_session
from app.core.models import WalletCluster
from app.services.clustering import cluster_engine

router = APIRouter(prefix="/clusters", tags=["clusters"])

_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _validate(address: str) -> str:
    if not _ADDR_RE.match(address):
        raise HTTPException(status_code=400, detail="malformed_address")
    return address.lower()


def _read_cache(session: Session, address: str) -> WalletCluster | None:
    return session.get(WalletCluster, address)


def _write_cache(session: Session, result: ClusterResult, ttl_days: int) -> None:
    payload = result.model_dump(mode="json")
    expires = datetime.now(UTC) + timedelta(days=ttl_days)
    stmt = insert(WalletCluster).values(
        address=result.address,
        computed_at=result.computed_at,
        ttl_expires_at=expires,
        payload=payload,
    ).on_conflict_do_update(
        index_elements=["address"],
        set_={
            "computed_at": result.computed_at,
            "ttl_expires_at": expires,
            "payload": payload,
        },
    )
    session.execute(stmt)
    session.commit()


def _hydrate_stale(row: WalletCluster) -> ClusterResult:
    data = dict(row.payload)
    data["stale"] = True
    return ClusterResult.model_validate(data)


async def _compute_for_address(address: str) -> ClusterResult:
    settings = get_settings()
    if not settings.etherscan_api_key:
        raise EtherscanUnavailable("ETHERSCAN_API_KEY not configured")
    async with httpx.AsyncClient(base_url=ETHERSCAN_BASE_URL, timeout=20.0) as http:
        client = EtherscanClient(http, api_key=settings.etherscan_api_key)
        return await cluster_engine.compute(
            client,
            address,
            max_linked=settings.cluster_max_linked_wallets,
            max_deposit_candidates=settings.cluster_max_deposit_candidates,
            funder_strong_threshold=settings.cluster_funder_strong_threshold,
        )


@router.get("/{address}", response_model=ClusterResult)
async def get_cluster(
    address: str,
    session: Annotated[Session, Depends(get_session)],
) -> ClusterResult:
    addr = _validate(address)
    settings = get_settings()
    row = _read_cache(session, addr)
    now = datetime.now(UTC)
    if row is not None and row.ttl_expires_at > now:
        return ClusterResult.model_validate(row.payload)

    try:
        result = await _compute_for_address(addr)
    except (EtherscanUnavailable, EtherscanRateLimited):
        if row is not None:
            return _hydrate_stale(row)
        raise HTTPException(status_code=503, detail="etherscan_unavailable")

    _write_cache(session, result, settings.cluster_cache_ttl_days)
    return result


@router.post("/{address}/refresh", response_model=ClusterResult)
async def refresh_cluster(
    address: str,
    session: Annotated[Session, Depends(get_session)],
) -> ClusterResult:
    addr = _validate(address)
    settings = get_settings()
    try:
        result = await _compute_for_address(addr)
    except (EtherscanUnavailable, EtherscanRateLimited):
        row = _read_cache(session, addr)
        if row is not None:
            return _hydrate_stale(row)
        raise HTTPException(status_code=503, detail="etherscan_unavailable")
    _write_cache(session, result, settings.cluster_cache_ttl_days)
    return result
