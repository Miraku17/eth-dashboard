# Stablecoin volume — moving-average overlay (design)

**Date:** 2026-05-11
**Status:** spec, awaiting plan
**Author:** Claude / operator pair

## Problem

`LiveVolumePanel` shows per-minute on-chain stablecoin transfer volume as a
stacked area, refreshing every ~5s. It answers "what's happening *now*" but not
"is flow rising or falling, and how does the latest minute compare to the
recent norm?". The operator wants trend/momentum signal on top of the existing
NOW data — without a new panel or new backend.

## Goal

Add moving-average overlays + a "current vs trend" headline tile to
`LiveVolumePanel` so a glance at the chart answers:

1. Is stable transfer volume **trending up or down** right now?
2. How does the **current minute** compare to the recent baseline?

No backend changes. Pure client-side derivation from the minute buckets the
panel already fetches.

## Non-goals

- Per-asset MA breakdown (asset-level surge detection lands later if useful — out of scope here).
- Z-scores / regime classification — that's a richer, separate panel (Option B in the brainstorm).
- Backend endpoint, new table, or persistence of any kind.
- Mint/burn (supply Δ) trend — that's `StablecoinSupplyPanel`'s domain.

## Approach

Compute two simple moving averages of the **total** per-minute USD volume
(sum across all stable assets in the current window) and overlay them as
Recharts `<Line>` elements on top of the existing stacked `<Area>` chart.
Add one headline tile above the chart that reports `current minute vs slow MA`
as a signed % with an up/down arrow.

### MA windows per range

Window selections come from the existing `RANGE_OPTIONS` (15m / 1h / 4h / 24h).
Fast and slow MA periods are picked per range so both lines have enough
samples to be smooth without flattening into the slow MA.

| Window | Fast MA | Slow MA |
| ------ | ------- | ------- |
| 15m    | 3m      | 10m     |
| 1h     | 5m      | 30m     |
| 4h     | 15m     | 60m     |
| 24h    | 60m     | 240m    |

Defined as a constant `MA_PERIODS_BY_WINDOW` next to `RANGE_OPTIONS`. Edge
case: if the rendered series has fewer rows than the slow period
(e.g. listener just started, only 4 minutes of data on a 15m window), the
slow line skips rendering for those leading rows — same for fast. No "NaN
dragged across the chart."

### Computation

In the existing `pivot()` helper (or a new sibling helper):

1. After `byTs` is built and sorted, iterate the sorted rows and compute
   `total = sum(row[asset] for asset in assetSet)` per row, attaching it as
   `row._total`.
2. Compute `row._fastMA` and `row._slowMA` as trailing rolling means of
   `_total` with periods pulled from `MA_PERIODS_BY_WINDOW[minutes]`. Set
   to `undefined` (not 0) for rows with insufficient look-back so Recharts
   leaves a gap instead of plotting a misleading point.

Implementation note: use a single trailing-window pass per period
(running sum, subtract dropping element, divide by current population) — O(n)
per series. Trivial cost on the 15-1440 row range.

### Rendering

Inside the existing `<AreaChart>`:

- Keep all `<Area>` elements unchanged (per-asset stacked on `stackId="vol"`).
- Add two `<Line type="monotone" dataKey="_fastMA" />` and
  `<Line dataKey="_slowMA" />` after the areas. Both with
  `dot={false}`, `strokeWidth={1.5}`, and `connectNulls={false}` so the
  leading-gap behavior actually renders as a gap.
- Colors: fast = `rgb(251 191 36)` (amber-400, draws the eye), slow =
  `rgb(148 163 184)` (slate-400, muted reference). Avoid asset palette
  colors so the lines are visually distinct from the stack underneath.
- Tooltip: extend the existing formatter so `_fastMA` / `_slowMA` rows show
  with friendly labels (`"{fastPeriod}m MA"` / `"{slowPeriod}m MA"`, derived
  from the period table) rather than the raw key.

### Headline tile

A single line above the chart, between the existing
"N minutes shown · window total" row and the `<DataAge>` line. With the 1h
window selected (slow period = 30m), it would read:

```
$1.24M / min · +38% vs 30m avg ▲
```

The `30m` segment is `{slowPeriod}m`, derived from the period table, not
hardcoded.

- Left: most-recent-minute total USD/min.
- Right: signed % delta of `lastTotal / lastSlowMA - 1`, tinted `text-up`
  if positive / `text-down` if negative / `text-slate-500` if absolute
  delta < 5% (treat as flat).
- Arrow `▲` / `▼` / `→` matches the tint.
- If the slow MA hasn't warmed up yet (`undefined` on the last row), render
  `"warming up — {slowPeriod}m baseline in {N}m"` where N is
  `slowPeriod - rowsSoFar`.
  This keeps the operator from seeing a meaningless +∞ on first paint.

### Legend

Extend the existing per-asset legend grid: append two rows at the top labelled
"5m MA" and "30m MA" (label text driven by the period table, not hardcoded)
with the corresponding swatch color. They render above the asset legend so
the eye lands on trend first.

## Files touched

Single file: `frontend/src/components/LiveVolumePanel.tsx`. No new files,
no API changes, no schema changes.

Constants `MA_PERIODS_BY_WINDOW` and the rolling-mean helper live in the same
file — small enough that a separate util doesn't earn its keep.

## Testing

- Manual: open the panel on each of the four windows, confirm:
  - Both MA lines render once enough samples exist.
  - Lines truncate cleanly at the left edge during warm-up (gap, not 0).
  - Headline tile flips `▲ / ▼ / →` and color when flow accelerates /
    decelerates / sits flat.
  - Tooltip shows asset stack + both MAs with labelled rows.
- Regression: existing stacked area still renders, asset legend still works,
  per-minute "current per asset" tiles unchanged.
- No new unit tests — the rolling-mean math is too small to earn one and is
  implicitly verified by eyeballing line continuity on the chart. (If we
  later extract the helper for reuse, that earns a test then, not now.)

## Risks / open questions

- **24h window with 240m slow MA:** on the very first hours of a fresh deploy
  the slow line won't render at all. Headline tile's "warming up" copy
  covers that case; chart simply has no slow line. Acceptable.
- **Spiky single minutes** (e.g. one $50M USDT transfer to a CEX) will
  yank the fast MA. That's correct behavior — operator wants to see those
  surges — but worth flagging that the fast line will be noisier than the
  slow one. No smoothing beyond the MA itself.
- **Color contrast:** amber on the existing dark surface should pop, but
  worth a sanity check against the panel-responsive narrow-mode classes
  during manual QA.

## Out of scope (deferred follow-ups)

If this lands and the operator wants more, natural next steps — each as
its own brainstorm:

1. **Per-asset MA crosses** — flag when an individual asset's fast > slow
   for the first time in N hours.
2. **Z-score vs trailing 24h baseline** — surface "this hour is +2σ" tiles.
3. **Promote to a standalone `Stable volume momentum` panel** if the
   overlay starts feeling cramped.
