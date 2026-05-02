# Flow Panels Polish — Design

**Status:** approved 2026-05-02
**Track:** UI polish (follow-up to stablecoin coverage round 2)
**Related specs:**
- `2026-05-02-stablecoin-coverage-round-2-design.md` (round 2 added EUR/GBP coverage; this PR makes the panels show what we now collect)

## Goal

The Stablecoin Supply Δ and Exchange Netflows panels both collapse two opposing legs (mints/burns, deposits/withdrawals) into a single signed bar. With 12 stables now flowing in (3 of which are non-USD), the net-only view hides:

- whether a number is "calm net" (small mints, small burns) or "high churn net" (huge mints, huge burns netting out)
- direction of motion within the selected range — is supply trending up or steady?
- which currency basket the stables belong to (USD vs EUR/GBP/CHF)

Polish both panels with: **two-leg divergent bar**, **inline sparkline of hourly net**, and (stablecoin panel only) **peg-currency section headers**.

## Non-goals

- No new data, schema, endpoint, or backend change. The `/api/flows/stablecoins` and `/api/flows/exchange` payloads already split direction and hourly bucket — everything is rendered client-side.
- No charting library. Sparkline is a hand-rolled inline `<svg>` (~30 lines).
- Not changing the panel header / range selector / overall card chrome.
- Not touching `OnchainVolumePanel` or `VolumeStructurePanel`.

## What changes

### Component: `Sparkline.tsx` (new, shared)

Small reusable inline-SVG sparkline. Takes an array of numbers (the per-hour net values, oldest → newest), renders a path. Width/height props (default 80×20). Auto-scales: y-axis range is `[min(values), max(values)]` with a midline at zero if the series crosses zero. Stroke color from prop (`up` / `down` / neutral). Optional area fill below the line at low opacity.

Rendering:
- Path is `M x0,y0 L x1,y1 ...` with linear interpolation.
- If all values are equal (or empty), renders a flat midline.
- If the series crosses zero, draws a faint horizontal zero-rule at y=0.

Tests: not strictly required (presentational SVG), but a tiny render smoke test is fine if convenient.

### `StablecoinSupplyPanel.tsx`

**Data shape:** today the panel sums `direction='in'` (mints) minus `direction='out'` (burns) per asset across all buckets to produce a single net. Extend this to also produce:

1. `mintTotal[asset]` — sum of `in` usd_value over the range
2. `burnTotal[asset]` — sum of `out` usd_value over the range
3. `hourlyNet[asset]` — `Map<ts_bucket, number>` of net per hour, sorted oldest → newest

**Row layout** (one per asset):

```
┌─────────────────────────────────────────────────────────────┐
│ USDT                                              +$48.2M   │  ← asset + net (signed, colored)
│ ▰▰▰▰▰▰▰▰▰▰▰▰▰▰━━━━━━━━━━━━━━━━━━━━━━━▱▱▱▱▱▱▱▱▱▱▱▱  ╱╲      │  ← divergent bar + sparkline
│ mint $128M / burn $80M                                      │  ← optional sub-line
└─────────────────────────────────────────────────────────────┘
```

- Divergent bar: a 1.5px-tall track split at center. Mint segment (green) extends rightward proportional to mint USD; burn segment (red) extends leftward proportional to burn USD. Each leg's max width is half the row width. Scale across all assets in the panel uses `max(maxMint, maxBurn)` so legs stay comparable.
- Sparkline: 80×20 SVG, color-coded green if final value ≥ 0 else red. Same height as the bar's row, sits inline at the right margin.
- Sub-line: small muted text `mint $X / burn $Y` for non-zero pegs only. Hidden when zoom mode (`@xs`) is active to keep narrow panels tight.

**Peg grouping:** Group rows by peg currency, in order USD, EUR, GBP, CHF. A small all-caps muted header (`USD STABLES`, `EUR STABLES`, etc.) precedes each group. Empty groups (no rows with data) are not rendered. Inside a group, rows are sorted by `|net|` descending (same heuristic as today, scoped to the group).

The panel uses a `lib/peg.ts` map: `{ USDT: "USD", USDC: "USD", ..., EURCV: "EUR", EURe: "EUR", tGBP: "GBP", ZCHF: "CHF" }`. Unknown asset → "OTHER" group rendered last (defensive — shouldn't fire).

### `ExchangeFlowsPanel.tsx`

Same divergent-bar + sparkline pattern, but the legs are inflow (positive, money INTO the CEX, deposits) vs outflow (negative, money OUT of the CEX, withdrawals). Sub-line is `in $X / out $Y`. No peg grouping — exchanges aren't currencies.

### `lib/peg.ts` (new)

Mirrors backend `STABLES.peg_currency` for the 12 known stables. Hand-maintained — when round 3 adds new stables, this map updates alongside `tokens.py` (one extra line per stable; round-2 PR has already established the pattern).

## Visual / UX details

- Divergent bar lives in the existing 1.5px-tall track (`h-1.5`). Two child divs, one anchored left of center, one anchored right of center. Center is fixed at 50% — both legs share the half-width budget.
- Sparkline is intentionally tiny (80×20 ≈ thumb-width). Goal: trend at-a-glance, not precision. No tooltip.
- Color tokens: existing `text-up` / `text-down` / `bg-up/80` / `bg-down/80` (already in tailwind config).
- Container queries: when the panel is squeezed to `@xs` (narrow column), hide the sub-line and shrink sparkline to 60×16. Already-existing `<PanelShell>` `@container` wrap means we just use Tailwind `@xs:hidden` etc.
- Empty state: same as today (`no data yet — waiting for Dune sync`).

## Risks / known limits

- **Single-bucket case:** if the selected range is `24h` and Dune has only delivered a couple of buckets, the sparkline can be 1–2 points. The component handles 0/1 points (flat midline); 2+ points is fine.
- **Big EUROC numbers next to small tGBP:** the bar scaling is per-panel-max so tGBP rows can look near-flat. That's accurate (it really is small) — not a bug. Consider a future "normalize per row" toggle if it becomes a complaint. Out of scope.
- **No sparkline in `@xs` super-narrow:** mobile / small bento cell. Acceptable — the divergent bar still tells the main story.

## Tests

Pure presentational frontend. No new backend tests. No new frontend tests required (the existing `npm run build` / typecheck is the gate). If a Sparkline test feels worthwhile, one rtl render smoke test is fine; otherwise skip.

## Future work

- Click a stablecoin row → drawer with full mints+burns time series and minter/burner addresses (echoes the wallet drawer pattern).
- Per-row toggle USD ↔ native units (e.g., display in EUR for EUR stables when their group is selected). Out of scope here.
- "Top movers" view that pivots from the per-asset list to a leaderboard of largest 1h spikes.
