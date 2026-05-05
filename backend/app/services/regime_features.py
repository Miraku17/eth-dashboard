"""Feature gatherer for the market-regime classifier (v4 card 9).

Pulls each of the six features the regime kernel needs from the existing
tables. Returns a list of `FeatureZ` rows ready for `score_regime`.

All windowing here uses the single source of truth: `now()` minus a
fixed lookback. Each feature carries a 30-day baseline computed from
hour-bucket aggregates (mean + std) of the same metric.

Cost-sensitive design: each feature is one query (the 30d baseline + the
24h current value share the same SQL window), and the whole gatherer
runs in <100ms against a healthy Postgres. The endpoint caches the full
result for 60s, so even a large user base hits the DB at most once a
minute.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.models import (
    DerivativesSnapshot,
    DexSwap,
    StakingFlow,
    Transfer,
    VolumeBucket,
    WalletScore,
)
from app.realtime.flow_classifier import FlowKind
from app.services.regime import DEFAULT_WEIGHTS, FeatureZ, make_feature

# Window constants. The "current" pane is 24h; the baseline is 30d of
# 24h-rolling samples bucketed by day (29 prior daily samples + today).
CURRENT_WINDOW_HOURS = 24
BASELINE_DAYS = 30
SMART_MONEY_TOP_N = 100  # wallets considered "smart money" by current score


@dataclass(frozen=True)
class FeatureSummary:
    """Augments FeatureZ with an `as_of` timestamp so the panel can
    surface staleness per feature (smart-money is daily, funding is
    hourly, etc.)."""
    feature: FeatureZ
    as_of: datetime | None


def _hourly_to_daily_stats(values_by_day: list[float]) -> tuple[float, float]:
    """Mean + population std of a list of daily samples. Returns (0,0)
    for an empty or single-element list (the kernel treats std=0 as
    'no signal')."""
    n = len(values_by_day)
    if n < 2:
        return 0.0, 0.0
    mean = sum(values_by_day) / n
    variance = sum((v - mean) ** 2 for v in values_by_day) / n
    return mean, variance ** 0.5


def _cex_flow_feature(session: Session, now: datetime) -> FeatureSummary:
    """Net USD flow into CEX hot wallets over the current 24h window vs.
    a 30-day daily baseline of the same metric.

    Sign convention: +inflow = bearish (positive z = bearish).
    """
    cur_cutoff = now - timedelta(hours=CURRENT_WINDOW_HOURS)
    base_cutoff = now - timedelta(days=BASELINE_DAYS)

    # Current 24h net flow.
    current = session.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (Transfer.flow_kind == FlowKind.WALLET_TO_CEX, Transfer.usd_value),
                        (Transfer.flow_kind == FlowKind.CEX_TO_WALLET, -Transfer.usd_value),
                        else_=0,
                    )
                ),
                0,
            )
        ).where(
            Transfer.ts >= cur_cutoff,
            Transfer.flow_kind.in_([FlowKind.WALLET_TO_CEX, FlowKind.CEX_TO_WALLET]),
        )
    ).scalar() or 0
    current = float(current)

    # Baseline: per-day net flow over the prior 30 days (excluding the
    # current 24h window so the baseline doesn't include the value we're
    # comparing to).
    daily_rows = session.execute(
        select(
            func.date_trunc("day", Transfer.ts).label("d"),
            func.coalesce(
                func.sum(
                    case(
                        (Transfer.flow_kind == FlowKind.WALLET_TO_CEX, Transfer.usd_value),
                        (Transfer.flow_kind == FlowKind.CEX_TO_WALLET, -Transfer.usd_value),
                        else_=0,
                    )
                ),
                0,
            ).label("net"),
        )
        .where(
            Transfer.ts >= base_cutoff,
            Transfer.ts < cur_cutoff,
            Transfer.flow_kind.in_([FlowKind.WALLET_TO_CEX, FlowKind.CEX_TO_WALLET]),
        )
        .group_by("d")
    ).all()
    daily_values = [float(r.net) for r in daily_rows]
    mean, std = _hourly_to_daily_stats(daily_values)

    feat = make_feature(
        name="cex_flow",
        raw=current,
        baseline_mean=mean,
        baseline_std=std,
        weight=DEFAULT_WEIGHTS["cex_flow"],
        bearish_when_positive=True,
    )
    latest_ts = session.execute(
        select(func.max(Transfer.ts)).where(
            Transfer.flow_kind.in_([FlowKind.WALLET_TO_CEX, FlowKind.CEX_TO_WALLET])
        )
    ).scalar()
    return FeatureSummary(feature=feat, as_of=latest_ts)


def _funding_feature(session: Session, now: datetime) -> FeatureSummary:
    """Current avg funding rate (latest snapshot per exchange averaged)
    vs. 30d hourly baseline. +funding = leverage long = bearish at
    extremes."""
    base_cutoff = now - timedelta(days=BASELINE_DAYS)
    latest_per_ex = session.execute(
        select(DerivativesSnapshot.exchange, func.max(DerivativesSnapshot.ts).label("mts"))
        .where(DerivativesSnapshot.funding_rate.is_not(None))
        .group_by(DerivativesSnapshot.exchange)
    ).all()

    current_vals: list[float] = []
    for row in latest_per_ex:
        v = session.execute(
            select(DerivativesSnapshot.funding_rate).where(
                DerivativesSnapshot.exchange == row.exchange,
                DerivativesSnapshot.ts == row.mts,
            )
        ).scalar()
        if v is not None:
            current_vals.append(float(v))
    current = sum(current_vals) / len(current_vals) if current_vals else 0.0

    # Baseline: hourly avg across all venues over 30d.
    hourly_rows = session.execute(
        select(
            func.date_trunc("hour", DerivativesSnapshot.ts).label("h"),
            func.avg(DerivativesSnapshot.funding_rate).label("avg_fr"),
        )
        .where(
            DerivativesSnapshot.ts >= base_cutoff,
            DerivativesSnapshot.funding_rate.is_not(None),
        )
        .group_by("h")
    ).all()
    samples = [float(r.avg_fr) for r in hourly_rows if r.avg_fr is not None]
    mean, std = _hourly_to_daily_stats(samples)

    feat = make_feature(
        name="funding",
        raw=current,
        baseline_mean=mean,
        baseline_std=std,
        weight=DEFAULT_WEIGHTS["funding"],
        bearish_when_positive=True,
    )
    latest_ts = session.execute(select(func.max(DerivativesSnapshot.ts))).scalar()
    return FeatureSummary(feature=feat, as_of=latest_ts)


def _oi_delta_feature(session: Session, now: datetime) -> FeatureSummary:
    """24h change in aggregate OI (USD across all venues) vs. 30-day
    daily baseline of the same delta. +OI rising = bearish bias."""
    cur_cutoff = now - timedelta(hours=CURRENT_WINDOW_HOURS)
    base_cutoff = now - timedelta(days=BASELINE_DAYS)

    def _agg_oi_at(at_or_before: datetime) -> float:
        # Latest OI per exchange at or before `at_or_before`, summed.
        sub = (
            select(
                DerivativesSnapshot.exchange,
                func.max(DerivativesSnapshot.ts).label("mts"),
            )
            .where(
                DerivativesSnapshot.ts <= at_or_before,
                DerivativesSnapshot.oi_usd.is_not(None),
            )
            .group_by(DerivativesSnapshot.exchange)
        ).subquery()
        total = session.execute(
            select(func.coalesce(func.sum(DerivativesSnapshot.oi_usd), 0)).join(
                sub,
                (DerivativesSnapshot.exchange == sub.c.exchange)
                & (DerivativesSnapshot.ts == sub.c.mts),
            )
        ).scalar() or 0
        return float(total)

    current_delta = _agg_oi_at(now) - _agg_oi_at(cur_cutoff)

    # Baseline: 30 daily deltas (each day vs. prior).
    daily_oi_rows = session.execute(
        select(
            func.date_trunc("day", DerivativesSnapshot.ts).label("d"),
            func.avg(DerivativesSnapshot.oi_usd).label("avg_oi"),
        )
        .where(
            DerivativesSnapshot.ts >= base_cutoff,
            DerivativesSnapshot.oi_usd.is_not(None),
        )
        .group_by("d")
        .order_by("d")
    ).all()
    daily_values = [float(r.avg_oi) for r in daily_oi_rows if r.avg_oi is not None]
    deltas = [
        daily_values[i] - daily_values[i - 1] for i in range(1, len(daily_values))
    ]
    mean, std = _hourly_to_daily_stats(deltas)

    feat = make_feature(
        name="oi_delta",
        raw=current_delta,
        baseline_mean=mean,
        baseline_std=std,
        weight=DEFAULT_WEIGHTS["oi_delta"],
        bearish_when_positive=True,
    )
    latest_ts = session.execute(
        select(func.max(DerivativesSnapshot.ts)).where(
            DerivativesSnapshot.oi_usd.is_not(None)
        )
    ).scalar()
    return FeatureSummary(feature=feat, as_of=latest_ts)


def _staking_flow_feature(session: Session, now: datetime) -> FeatureSummary:
    """Net staking flow (deposits minus withdrawals) over current 24h vs
    30d daily baseline. +deposits = bullish (sign-flip)."""
    cur_cutoff = now - timedelta(hours=CURRENT_WINDOW_HOURS)
    base_cutoff = now - timedelta(days=BASELINE_DAYS)

    def _net(start: datetime, end: datetime) -> float:
        rows = session.execute(
            select(StakingFlow.kind, func.coalesce(func.sum(StakingFlow.amount_eth), 0))
            .where(StakingFlow.ts_bucket >= start, StakingFlow.ts_bucket < end)
            .group_by(StakingFlow.kind)
        ).all()
        deposits = sum(float(amt) for kind, amt in rows if kind == "deposit")
        withdraws = sum(float(amt) for kind, amt in rows if kind != "deposit")
        return deposits - withdraws

    current = _net(cur_cutoff, now)

    # 30 daily samples.
    daily_rows = session.execute(
        select(
            func.date_trunc("day", StakingFlow.ts_bucket).label("d"),
            StakingFlow.kind,
            func.sum(StakingFlow.amount_eth).label("amt"),
        )
        .where(StakingFlow.ts_bucket >= base_cutoff, StakingFlow.ts_bucket < cur_cutoff)
        .group_by("d", StakingFlow.kind)
    ).all()
    by_day: dict[datetime, float] = {}
    for r in daily_rows:
        sign = 1.0 if r.kind == "deposit" else -1.0
        by_day[r.d] = by_day.get(r.d, 0.0) + sign * float(r.amt or 0)
    samples = list(by_day.values())
    mean, std = _hourly_to_daily_stats(samples)

    feat = make_feature(
        name="staking_flow",
        raw=current,
        baseline_mean=mean,
        baseline_std=std,
        weight=DEFAULT_WEIGHTS["staking_flow"],
        bearish_when_positive=False,
    )
    latest_ts = session.execute(select(func.max(StakingFlow.ts_bucket))).scalar()
    return FeatureSummary(feature=feat, as_of=latest_ts)


def _smart_money_feature(session: Session, now: datetime) -> FeatureSummary:
    """Net WETH (in USD) bought vs sold by the top-N smart-money wallets
    in the current 24h. +smart-money buying = bullish (sign-flip)."""
    cur_cutoff = now - timedelta(hours=CURRENT_WINDOW_HOURS)
    base_cutoff = now - timedelta(days=BASELINE_DAYS)

    top_wallets = session.execute(
        select(WalletScore.wallet)
        .where(WalletScore.score > 0)
        .order_by(WalletScore.score.desc())
        .limit(SMART_MONEY_TOP_N)
    ).scalars().all()
    if not top_wallets:
        feat = make_feature(
            name="smart_money_dir",
            raw=0,
            baseline_mean=0,
            baseline_std=0,
            weight=DEFAULT_WEIGHTS["smart_money_dir"],
            bearish_when_positive=False,
        )
        return FeatureSummary(feature=feat, as_of=None)

    wallet_set = list(top_wallets)

    def _net_buy_usd(start: datetime, end: datetime) -> float:
        return float(
            session.execute(
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (DexSwap.side == "buy", DexSwap.usd_value),
                                (DexSwap.side == "sell", -DexSwap.usd_value),
                                else_=0,
                            )
                        ),
                        0,
                    )
                ).where(
                    DexSwap.ts >= start,
                    DexSwap.ts < end,
                    DexSwap.wallet.in_(wallet_set),
                )
            ).scalar() or 0
        )

    current = _net_buy_usd(cur_cutoff, now)

    daily_rows = session.execute(
        select(
            func.date_trunc("day", DexSwap.ts).label("d"),
            DexSwap.side,
            func.sum(DexSwap.usd_value).label("usd"),
        )
        .where(
            DexSwap.ts >= base_cutoff,
            DexSwap.ts < cur_cutoff,
            DexSwap.wallet.in_(wallet_set),
        )
        .group_by("d", DexSwap.side)
    ).all()
    per_day: dict[datetime, float] = {}
    for r in daily_rows:
        sign = 1.0 if r.side == "buy" else -1.0
        per_day[r.d] = per_day.get(r.d, 0.0) + sign * float(r.usd or 0)
    samples = list(per_day.values())
    mean, std = _hourly_to_daily_stats(samples)

    feat = make_feature(
        name="smart_money_dir",
        raw=current,
        baseline_mean=mean,
        baseline_std=std,
        weight=DEFAULT_WEIGHTS["smart_money_dir"],
        bearish_when_positive=False,
    )
    latest_ts = session.execute(
        select(func.max(WalletScore.updated_at))
    ).scalar()
    return FeatureSummary(feature=feat, as_of=latest_ts)


def _volume_skew_feature(session: Session, now: datetime) -> FeatureSummary:
    """Whale-bucket share of DEX volume over 24h vs. 30d baseline.

    Whale-share spikes can mean either accumulation or distribution; per
    the v4 vision's framing they correlate with regime extremes. We
    treat +whale share = bearish (mild) since a whale-share spike late
    in a rally maps to distribution; the kernel's overall score
    determines whether it pushes toward euphoria or capitulation.
    """
    cur_cutoff = now - timedelta(hours=CURRENT_WINDOW_HOURS)
    base_cutoff = now - timedelta(days=BASELINE_DAYS)

    def _share(start: datetime, end: datetime) -> float:
        rows = session.execute(
            select(VolumeBucket.bucket, func.coalesce(func.sum(VolumeBucket.usd_value), 0))
            .where(VolumeBucket.ts_bucket >= start, VolumeBucket.ts_bucket < end)
            .group_by(VolumeBucket.bucket)
        ).all()
        total = sum(float(v) for _, v in rows)
        if total <= 0:
            return 0.0
        whale = sum(float(v) for k, v in rows if k == "whale")
        return whale / total

    current = _share(cur_cutoff, now)

    # 30 daily samples.
    daily_rows = session.execute(
        select(
            func.date_trunc("day", VolumeBucket.ts_bucket).label("d"),
            VolumeBucket.bucket,
            func.sum(VolumeBucket.usd_value).label("v"),
        )
        .where(VolumeBucket.ts_bucket >= base_cutoff, VolumeBucket.ts_bucket < cur_cutoff)
        .group_by("d", VolumeBucket.bucket)
    ).all()
    per_day_total: dict[datetime, float] = {}
    per_day_whale: dict[datetime, float] = {}
    for r in daily_rows:
        per_day_total[r.d] = per_day_total.get(r.d, 0.0) + float(r.v or 0)
        if r.bucket == "whale":
            per_day_whale[r.d] = per_day_whale.get(r.d, 0.0) + float(r.v or 0)
    samples = [
        per_day_whale.get(d, 0.0) / per_day_total[d]
        for d in per_day_total
        if per_day_total[d] > 0
    ]
    mean, std = _hourly_to_daily_stats(samples)

    feat = make_feature(
        name="volume_skew",
        raw=current,
        baseline_mean=mean,
        baseline_std=std,
        weight=DEFAULT_WEIGHTS["volume_skew"],
        bearish_when_positive=True,
    )
    latest_ts = session.execute(select(func.max(VolumeBucket.ts_bucket))).scalar()
    return FeatureSummary(feature=feat, as_of=latest_ts)


# ── Public entry point ────────────────────────────────────────────────


def gather_features(session: Session, now: datetime | None = None) -> list[FeatureSummary]:
    """Pull all six features. Each is independent — failures in one
    bubble up rather than being silently zeroed; the endpoint translates
    those into HTTP 503."""
    now = now or datetime.now(UTC)
    return [
        _cex_flow_feature(session, now),
        _funding_feature(session, now),
        _oi_delta_feature(session, now),
        _staking_flow_feature(session, now),
        _smart_money_feature(session, now),
        _volume_skew_feature(session, now),
    ]
