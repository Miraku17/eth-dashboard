"""v4 migration verification script.

Run from inside the worker container:

    docker compose exec -T worker python /app/scripts/v4-verify.py

(or pipe via stdin: ``docker compose exec -T worker python < scripts/v4-verify.py``)

Checks every layer of the v4 migration end-to-end:

  1. address_label seeded with curated rows
  2. flow_kind populated on transfers
  3. Each migrated table has fresh data (rows newer than threshold)
  4. The realtime listener is alive (recent transfers)
  5. The beacon-flows cron has advanced its cursor recently

Each check prints PASS / WARN / FAIL with a one-line reason. Exit code
0 if every check is PASS or WARN; non-zero if any FAIL.

Use after every deploy that touches the v4 surface, or whenever a
panel looks stale and you want to know which layer is at fault.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.db import get_sessionmaker
from app.core.models import (
    AddressLabel,
    OrderFlow,
    StablecoinFlow,
    StakingFlow,
    StakingFlowByEntity,
    Transfer,
    VolumeBucket,
)


# Disable color escapes when stdout isn't a TTY (e.g. piped to a file or
# captured by `docker compose exec -T`). Avoids junk like '\033[32m' showing
# up in logs.
if sys.stdout.isatty():
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    DIM = "\033[2m"
    RESET = "\033[0m"
else:
    GREEN = YELLOW = RED = DIM = RESET = ""

_results: list[tuple[str, str, str]] = []  # (level, name, message)


def _record(level: str, name: str, msg: str) -> None:
    _results.append((level, name, msg))
    color = {"PASS": GREEN, "WARN": YELLOW, "FAIL": RED}[level]
    print(f"  {color}{level:<4}{RESET}  {name:<38}  {DIM}{msg}{RESET}")


def section(title: str) -> None:
    print(f"\n{title}")


def now_utc() -> datetime:
    return datetime.now(UTC)


def main() -> int:
    SessionLocal = get_sessionmaker()
    s = SessionLocal()
    now = now_utc()

    section("== Foundation ==")

    # 1. address_label has the curated set.
    n_labels = s.query(AddressLabel).count()
    if n_labels >= 100:
        _record("PASS", "address_label rows", f"{n_labels} labels (>=100 expected)")
    elif n_labels > 0:
        _record("WARN", "address_label rows", f"{n_labels} (seed may be stale; check seed_revision)")
    else:
        _record("FAIL", "address_label rows", "0 — seeder hasn't run; check worker startup logs")

    # Per-category sanity.
    by_cat = dict(s.execute(
        select(AddressLabel.category, func.count()).group_by(AddressLabel.category)
    ).all())
    if by_cat.get("cex", 0) >= 10:
        _record("PASS", "  cex labels", f"{by_cat.get('cex', 0)} hot wallets")
    else:
        _record("WARN", "  cex labels", f"only {by_cat.get('cex', 0)} — CEX flow tile will under-attribute")
    if by_cat.get("staking", 0) >= 5:
        _record("PASS", "  staking labels", f"{by_cat.get('staking', 0)} contracts")
    else:
        _record("WARN", "  staking labels", f"only {by_cat.get('staking', 0)}")

    section("== Live classifier (transfers.flow_kind) ==")

    # 2. flow_kind populated.
    null_count = s.execute(
        select(func.count()).select_from(Transfer).where(Transfer.flow_kind.is_(None))
    ).scalar() or 0
    total = s.query(Transfer).count()
    if total == 0:
        _record("WARN", "transfers", "table empty — listener hasn't run yet")
    elif null_count == 0:
        _record("PASS", "flow_kind coverage", f"{total}/{total} transfers classified")
    elif null_count < total * 0.05:
        _record("PASS", "flow_kind coverage",
                f"{total - null_count}/{total} ({null_count} null — backfill may still be running)")
    else:
        _record("FAIL", "flow_kind coverage",
                f"{null_count}/{total} null — backfill cron didn't run")

    # Distribution.
    if total > 0:
        kinds = dict(s.execute(
            select(Transfer.flow_kind, func.count()).group_by(Transfer.flow_kind)
        ).all())
        cex_total = (kinds.get("wallet_to_cex") or 0) + (kinds.get("cex_to_wallet") or 0)
        share = cex_total / total * 100 if total else 0
        if share >= 5:
            _record("PASS", "  CEX flow share", f"{cex_total} CEX-tagged ({share:.1f}% — typical)")
        elif share > 0:
            _record("WARN", "  CEX flow share", f"only {share:.1f}% — CEX label coverage may be too narrow")
        else:
            _record("FAIL", "  CEX flow share", "no CEX-tagged transfers — labels missing or classifier broken")

    section("== Live aggregators (replaces Dune) ==")

    # 3. Migrated tables have FRESH data (last write within window).
    #    realtime_volume + stablecoin_flows + order_flow flush hourly.
    #    staking_flows updates every 5 min via beacon cron.
    fresh_window_hourly = now - timedelta(hours=2)
    fresh_window_5min = now - timedelta(minutes=15)

    def _check_freshness(label: str, model, ts_attr: str, fresh_within: datetime) -> None:
        latest = s.execute(
            select(getattr(model, ts_attr)).order_by(getattr(model, ts_attr).desc()).limit(1)
        ).scalar()
        if latest is None:
            _record("WARN", label, "no rows yet (listener / cron just started?)")
            return
        age = now - latest
        if latest >= fresh_within:
            _record("PASS", label, f"latest at {latest.isoformat()[:19]} ({_age_str(age)} ago)")
        else:
            _record("FAIL", label, f"stale: latest at {latest.isoformat()[:19]} ({_age_str(age)} ago)")

    _check_freshness("stablecoin_flows", StablecoinFlow, "ts_bucket", fresh_window_hourly)
    _check_freshness("staking_flows", StakingFlow, "ts_bucket", fresh_window_5min)
    _check_freshness("staking_flows_by_entity", StakingFlowByEntity, "ts_bucket", fresh_window_5min)
    _check_freshness("volume_buckets", VolumeBucket, "ts_bucket", fresh_window_hourly)

    # order_flow needs a freshness AND a per-DEX coverage check.
    of_latest = s.execute(
        select(OrderFlow.ts_bucket).order_by(OrderFlow.ts_bucket.desc()).limit(1)
    ).scalar()
    if of_latest is None:
        _record("WARN", "order_flow", "no rows")
    else:
        age = now - of_latest
        level = "PASS" if of_latest >= fresh_window_hourly else "FAIL"
        _record(level, "order_flow", f"latest {of_latest.isoformat()[:19]} ({_age_str(age)})")

        # Each named DEX should have at least one row in the last 24h.
        cutoff_24h = now - timedelta(hours=24)
        for dex in ("uniswap_v2", "uniswap_v3", "curve", "balancer"):
            n = s.execute(
                select(func.count()).select_from(OrderFlow).where(
                    OrderFlow.ts_bucket >= cutoff_24h, OrderFlow.dex == dex
                )
            ).scalar() or 0
            if n > 0:
                _record("PASS", f"  {dex}", f"{n} rows in last 24h")
            else:
                _record("WARN", f"  {dex}", "no rows in last 24h — pool registry may need expansion")

    section("== Realtime listener heartbeat ==")

    # 4. transfers row landed within last 30 min → listener is processing blocks.
    latest_t = s.execute(
        select(Transfer.ts).order_by(Transfer.ts.desc()).limit(1)
    ).scalar()
    if latest_t is None:
        _record("WARN", "transfers heartbeat", "no rows; listener may be idle")
    else:
        age = now - latest_t
        if age < timedelta(minutes=30):
            _record("PASS", "transfers heartbeat", f"latest whale {_age_str(age)} ago")
        elif age < timedelta(hours=2):
            _record("WARN", "transfers heartbeat", f"latest {_age_str(age)} ago — quiet market or slow listener")
        else:
            _record("FAIL", "transfers heartbeat", f"latest {_age_str(age)} ago — listener stuck?")

    s.close()

    # ── Summary ──
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for level, _, _ in _results:
        counts[level] += 1
    total_n = sum(counts.values())
    print(
        f"\nSummary: "
        f"{GREEN}{counts['PASS']} pass{RESET}  "
        f"{YELLOW}{counts['WARN']} warn{RESET}  "
        f"{RED}{counts['FAIL']} fail{RESET}  "
        f"({total_n} checks total)"
    )
    return 1 if counts["FAIL"] > 0 else 0


def _age_str(delta: timedelta) -> str:
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86_400:
        return f"{s // 3600}h"
    return f"{s // 86_400}d"


if __name__ == "__main__":
    sys.exit(main())
