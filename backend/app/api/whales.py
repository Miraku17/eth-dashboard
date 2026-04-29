from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    PendingTransferOut,
    PendingTransfersResponse,
    WhaleTransfer,
    WhaleTransfersResponse,
)
from app.core.db import get_session
from app.core.models import PendingTransfer, Transfer
from app.realtime.labels import label_for

router = APIRouter(prefix="/whales", tags=["whales"])


@router.get("/transfers", response_model=WhaleTransfersResponse)
def whale_transfers(
    session: Annotated[Session, Depends(get_session)],
    hours: int = Query(24, ge=1, le=24 * 30),
    asset: str | None = Query(None, description="filter: ETH, USDT, USDC, DAI"),
    limit: int = Query(100, ge=1, le=1000),
) -> WhaleTransfersResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = select(Transfer).where(Transfer.ts >= cutoff)
    if asset:
        stmt = stmt.where(Transfer.asset == asset.upper())
    rows = session.execute(stmt.order_by(Transfer.ts.desc()).limit(limit)).scalars().all()
    return WhaleTransfersResponse(
        transfers=[
            WhaleTransfer(
                tx_hash=r.tx_hash,
                log_index=r.log_index,
                block_number=r.block_number,
                ts=r.ts,
                from_addr=r.from_addr,
                to_addr=r.to_addr,
                from_label=label_for(r.from_addr),
                to_label=label_for(r.to_addr),
                asset=r.asset,
                amount=float(r.amount),
                usd_value=float(r.usd_value) if r.usd_value is not None else None,
            )
            for r in rows
        ]
    )


@router.get("/pending", response_model=PendingTransfersResponse)
def pending_whales(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(20, ge=1, le=200),
    asset: str | None = Query(None, description="filter: ETH, USDT, USDC, DAI"),
) -> PendingTransfersResponse:
    stmt = select(PendingTransfer)
    if asset:
        stmt = stmt.where(PendingTransfer.asset == asset.upper())
    # Pull 2× then dedupe by (from, to, asset, amount). Bots commonly
    # broadcast the same payload across many nonces / replacements; without
    # this the table fills with N copies of the same transfer.
    rows = (
        session.execute(stmt.order_by(PendingTransfer.seen_at.desc()).limit(limit * 2))
        .scalars()
        .all()
    )
    seen: set[tuple[str, str, str, float]] = set()
    deduped: list[PendingTransfer] = []
    for r in rows:
        key = (r.from_addr, r.to_addr, r.asset, float(r.amount))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
        if len(deduped) >= limit:
            break

    return PendingTransfersResponse(
        pending=[
            PendingTransferOut(
                tx_hash=r.tx_hash,
                from_addr=r.from_addr,
                to_addr=r.to_addr,
                from_label=label_for(r.from_addr),
                to_label=label_for(r.to_addr),
                asset=r.asset,
                amount=r.amount,
                usd_value=r.usd_value,
                seen_at=r.seen_at,
                nonce=r.nonce,
                gas_price_gwei=float(r.gas_price_gwei) if r.gas_price_gwei is not None else None,
            )
            for r in deduped
        ]
    )
