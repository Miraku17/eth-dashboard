from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    PendingTransferOut,
    PendingTransfersResponse,
    WhaleTransfer,
    WhaleTransfersResponse,
)
from app.core.db import get_session
from app.core.models import PendingTransfer, Transfer, WalletScore
from app.realtime.labels import label_for

router = APIRouter(prefix="/whales", tags=["whales"])

# Mirrors `SMART_FLOOR_USD` in WhaleTransfersPanel.tsx — keep in sync if
# the frontend tier moves. Below this, a wallet's PnL is panel-noise, not
# signal worth filtering on.
SMART_FLOOR_USD = 100_000.0


@router.get("/transfers", response_model=WhaleTransfersResponse)
def whale_transfers(
    session: Annotated[Session, Depends(get_session)],
    hours: int = Query(24, ge=1, le=24 * 30),
    asset: str | None = Query(None, description="filter: ETH, USDT, USDC, DAI"),
    flow_kind: list[str] | None = Query(
        None,
        description=(
            "v4: filter by classified flow_kind. Multi-select with "
            "?flow_kind=wallet_to_cex&flow_kind=cex_to_wallet. Values: "
            "wallet_to_cex / cex_to_wallet / wallet_to_dex / dex_to_wallet / "
            "lending_deposit / lending_withdraw / staking_deposit / "
            "staking_unstake / bridge_l2 / bridge_l2_withdraw / "
            "hyperliquid_in / hyperliquid_out / wallet_to_wallet."
        ),
    ),
    limit: int = Query(100, ge=1, le=1000),
    smart_only: bool = Query(
        False,
        description=(
            "v5: when true, only return transfers where at least one party is a "
            "smart-money wallet (wallet_score.score >= $100k 30d realized PnL)."
        ),
    ),
) -> WhaleTransfersResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = select(Transfer).where(Transfer.ts >= cutoff)
    if asset:
        stmt = stmt.where(Transfer.asset == asset.upper())
    if flow_kind:
        stmt = stmt.where(Transfer.flow_kind.in_(flow_kind))
    if smart_only:
        # WalletScore.wallet is stored lowercase by the scoring cron;
        # transfer addresses retain mixed case from the chain, so lowercase
        # both sides for the IN-clause comparison.
        smart_wallets = select(WalletScore.wallet).where(
            WalletScore.score >= SMART_FLOOR_USD
        )
        stmt = stmt.where(
            or_(
                func.lower(Transfer.from_addr).in_(smart_wallets),
                func.lower(Transfer.to_addr).in_(smart_wallets),
            )
        )
    rows = session.execute(stmt.order_by(Transfer.ts.desc()).limit(limit)).scalars().all()

    # v4: enrich with wallet_score for both sides of every transfer in a
    # single batched lookup (one IN-clause SELECT, not 2N round-trips).
    addrs: set[str] = set()
    for r in rows:
        addrs.add(r.from_addr.lower())
        addrs.add(r.to_addr.lower())
    score_rows = (
        session.execute(
            select(WalletScore.wallet, WalletScore.score, WalletScore.win_rate_30d)
            .where(WalletScore.wallet.in_(addrs))
        ).all()
        if addrs
        else []
    )
    scores: dict[str, tuple[float | None, float | None]] = {
        w: (float(s) if s is not None else None,
            float(wr) if wr is not None else None)
        for (w, s, wr) in score_rows
    }

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
                flow_kind=r.flow_kind,
                from_score=scores.get(r.from_addr.lower(), (None, None))[0],
                to_score=scores.get(r.to_addr.lower(), (None, None))[0],
                from_win_rate=scores.get(r.from_addr.lower(), (None, None))[1],
                to_win_rate=scores.get(r.to_addr.lower(), (None, None))[1],
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
