# Market Regime Classifier — Design

**Date:** 2026-05-04
**Status:** Draft
**Track:** v4 — card 9 (final card from `2026-05-03-v4-flow-classification-vision.md`)
**Predecessors:** v4 cards 1–5 live; v3 derivatives + smart-money already shipping data

## Goal

A single Overview tile that names the current market regime —
**Accumulation / Distribution / Euphoria / Capitulation / Neutral** — with a
confidence score and a transparent breakdown showing which features pushed
toward that label.

The vision doc lists this as the AI capstone. v1 ships the **rule-based**
version: a deterministic score over six existing features with hand-tuned
weights and thresholds. The vision doc itself flags AI as "later-stage";
shipping a transparent rule-based classifier first lets the user see the
output, judge the thresholds, and gives a future ML upgrade something to
benchmark against.

## Non-goals

- Trained ML model. The rule-based scorer ships first; ML is a follow-on.
- Historical regime backtesting / chart of past regimes. v1 is a single
  current-state tile. (We persist nothing; the score is computed on read
  from underlying tables that already retain history.)
- Per-asset regimes. ETH only. Same data scope as the rest of the dashboard.
- Real-time push / WebSocket. Tile re-fetches at 60s, sufficient for an
  hour-resolution signal.

## Six features

Each feature is z-scored against its own 30-day baseline, clipped to
[-3, +3], then multiplied by a sign convention that points "bearish" in
the positive direction. The score is a weighted sum of those signed z-scores.

| # | Feature                          | Source                                    | Sign convention                         |
|---|----------------------------------|-------------------------------------------|-----------------------------------------|
| 1 | CEX net flow (24h)               | `transfers WHERE flow_kind IN cex_*`      | +inflow → bearish (+)                   |
| 2 | Funding rate (avg, latest hour)  | `derivatives_snapshots.funding_rate`      | +funding → bearish (+) at extremes      |
| 3 | OI 24h delta (USD)               | `derivatives_snapshots.oi_usd`            | +OI rising → bearish bias (+)           |
| 4 | Staking net flow (24h, ETH)      | `staking_flows` deposits − withdrawals    | +deposits → bullish (−)                 |
| 5 | Smart-money 24h direction        | `dex_swap` joined `wallet_score` top-100  | +smart buying → bullish (−)             |
| 6 | Volume-bucket whale-share        | `volume_buckets` whale ÷ total            | +whale share → bearish at extremes (+)  |

**Why these six (and why not lending utilization):** The vision doc's list
included lending utilization, but Etherscope doesn't track utilization
directly today (the DeFi-TVL panel records protocol totals, not borrow vs.
supply ratios). Adding it would mean a new sync cron and table — out of
scope for v1. The other six signals are all already populated and refreshed
at hourly resolution or better.

## Scoring kernel

```python
# app/services/regime.py
@dataclass(frozen=True)
class FeatureZ:
    name: str
    raw: float
    z: float          # clipped, signed (positive = bearish)
    weight: float
    contribution: float  # z * weight

def score_regime(features: list[FeatureZ]) -> RegimeResult:
    total = sum(f.contribution for f in features)
    confidence = min(1.0, abs(total) / max_abs_score(features))
    label = label_for(total)
    return RegimeResult(label, total, confidence, features)
```

Weights (sum to 1.0):

```
cex_flow         0.25   # the v4 vision's stated 20× signal
funding          0.20
oi_delta         0.10
staking_flow     0.10
smart_money_dir  0.20
volume_skew      0.15
```

Label thresholds on the signed total:

```
total ≥ +1.5  → "distribution"   (mild bearish bias)
total ≥ +2.5  → "euphoria"        (extreme bearish — leverage stretched)
total ≤ -1.5  → "accumulation"    (mild bullish bias)
total ≤ -2.5  → "capitulation"    (extreme bullish — fear flush)
otherwise     → "neutral"
```

These are the v1 starting values. The kernel exposes them as named
constants so they're trivially tunable. Empirical re-tuning happens after
the panel has run for a week against real ETH price action.

## Schema

**No new tables.** The classifier is computed on read from existing
sources:

- `transfers` (with v4 `flow_kind` already populated)
- `derivatives_snapshots`
- `staking_flows`
- `dex_swap` + `wallet_score`
- `volume_buckets`

This keeps the build small and the output trivially cacheable in Redis
(60s TTL on `/api/regime`).

## API

```
GET /api/regime
→ {
    label: "neutral" | "accumulation" | "distribution" | "euphoria" | "capitulation",
    score: -0.42,                 # signed total
    confidence: 0.31,             # |score| / max_possible
    computed_at: "2026-05-04T17:32:00Z",
    features: [
      { name: "cex_flow",        z: 0.6,  weight: 0.25, contribution: 0.15,
        raw: 18_000_000.0,    # 24h net inflow USD
        baseline_mean: -2_000_000.0, baseline_std: 30_000_000.0 },
      …six rows…
    ]
  }
```

Response cached 60s in Redis under `regime:current`. The 30-day baseline
calculations are the expensive piece; they get their own 5-minute cache
keyed per feature so the tile stays cheap to refresh.

## What changes

### Backend

1. **New `app/services/regime.py`** — pure kernel. `compute_z`,
   `score_regime`, `label_for`. ~80 lines. Pure function over a feature
   dict; no DB access.
2. **New `app/services/regime_features.py`** — gathers each of the six
   features by querying the underlying tables. Returns the feature list
   ready for the kernel. ~120 lines.
3. **New `app/api/regime.py`** — single GET endpoint. Calls the gatherer,
   runs the kernel, wraps Redis cache. ~50 lines.
4. **`app/api/schemas.py`** — `RegimeFeature`, `RegimeResponse` models.
5. **`app/main.py`** — register the router under `AuthDep`.
6. **Tests** — `test_regime_kernel.py` covers the four regime corners
   plus the neutral case (5 unit tests, no DB), and a sixth test that
   verifies feature-contribution sums and confidence calc.

### Frontend

1. **`api.ts`** — `RegimeResponse` type + `fetchRegime()`. 60s refetch.
2. **New `MarketRegimePanel.tsx`** — compact tile:
   - Big label ("Distribution"), color-coded by category
   - Confidence ring or bar (0–100%)
   - Six small horizontal bars (one per feature) showing direction +
     contribution magnitude; tooltip shows raw + z values
3. **`panelRegistry.ts`** — register on the **Overview** page, default
   size S.

### Config

- No new env vars.
- `CLAUDE.md` — add `v4-market-regime` line under v4 status.

## Risks / known limits

- **Cold-start baseline noise.** First 30 days after deploy, the z-score
  baseline is short. The classifier may report "euphoria" or "capitulation"
  on routine moves until enough history accrues. Mitigation: clip z to
  [-3, +3] (already in the design) so a single outlier can't dominate, and
  the panel exposes the raw-vs-baseline tooltip so the operator can see
  what's driving the label.
- **Feature staleness mismatch.** Funding rates refresh hourly, smart-money
  scores update daily. A "neutral → distribution" flip caused entirely by
  the daily wallet_score refresh will look mysterious. Mitigation: each
  feature carries its `as_of` timestamp in the response; the tile shows
  the oldest as the regime's freshness.
- **Threshold tuning is empirical.** Initial weights are best-guess.
  Real validation is the user looking at the output for a week and
  saying "that flip was wrong." The kernel makes thresholds named
  constants, not magic numbers, so adjustments are a one-line change.
- **No backtest in v1.** We can't say "this label was right 70% of the
  time." That requires snapshotting the score per hour over weeks, which
  is straightforward to add later (one table, one cron) but inflates
  scope now.

## Future work

- **ML upgrade.** Once the rule-based version has been live for a few
  weeks, snapshot `(features, score, label, ETH 24h forward return)` per
  hour into a new `regime_history` table. Feed that into a small classifier
  (logistic regression or gradient boosted tree) and serve its label
  alongside the rule-based one. The rule-based classifier becomes the
  baseline against which the ML version proves its keep.
- **Lending utilization.** Add an Aave V3 + Compound V3 utilization sync
  cron that reads `getReserveData` per market, store hourly, and slot it
  into the kernel as a seventh feature.
- **Historical regime chart.** Once `regime_history` exists for ML, render
  it as a small timeline strip on the panel — "regime path over the last
  7 days."
- **Per-regime alerts.** "Notify me when the regime flips to euphoria or
  capitulation." Reuses the v1 alerts engine.
