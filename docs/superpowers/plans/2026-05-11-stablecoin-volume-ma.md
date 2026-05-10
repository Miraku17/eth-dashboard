# Stablecoin volume MA overlay — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fast/slow moving-average overlays + a "current vs trend" headline tile to `LiveVolumePanel`, so a glance shows whether on-chain stablecoin transfer volume is accelerating or cooling off.

**Architecture:** Pure client-side derivation from the per-minute volume points the panel already fetches. Compute total-per-minute, then rolling means with periods picked per selected window. Render as two Recharts `<Line>` overlays on the existing stacked `<AreaChart>` plus one headline copy line. Single file changed.

**Tech Stack:** React 18, Recharts, TanStack Query, TypeScript. Existing helpers: `formatUsdCompact`, `rgbOf`, `Card`, `DataAge`, `SimpleSelect`.

**Spec:** `docs/superpowers/specs/2026-05-11-stablecoin-volume-ma-design.md`

---

## File Structure

Single file modified:

- `frontend/src/components/LiveVolumePanel.tsx`
  - Add `MA_PERIODS_BY_WINDOW` constant beside `RANGE_OPTIONS`.
  - Extend `pivot()` (or add a sibling `enrich()` helper) to attach `_total`, `_fastMA`, `_slowMA` to each row, and to surface `fastPeriod` / `slowPeriod` / `lastTotal` / `lastSlowMA` for the headline tile.
  - Render two `<Line>` elements inside the existing `<AreaChart>` after the asset `<Area>` stack.
  - Add a headline-tile line above the existing "minutes shown · window total" row.
  - Extend the legend to prepend two MA rows.
  - Customize Recharts `<Tooltip>` formatter to label MA rows with `{period}m MA`.

No new files. No backend changes.

---

## Task 1: Add MA period table + rolling-mean helper

**Files:**
- Modify: `frontend/src/components/LiveVolumePanel.tsx`

- [ ] **Step 1: Add `MA_PERIODS_BY_WINDOW` constant after `RANGE_OPTIONS` (around line 25)**

Insert immediately after the `RANGE_OPTIONS` array:

```ts
type MAPeriods = { fast: number; slow: number };

// Fast / slow moving-average periods (in minutes) per window selection.
// Picked so both lines have enough samples to be smooth without flattening
// into the slow MA. Keep keys aligned with RANGE_OPTIONS.value.
const MA_PERIODS_BY_WINDOW: Record<number, MAPeriods> = {
  15: { fast: 3, slow: 10 },
  60: { fast: 5, slow: 30 },
  240: { fast: 15, slow: 60 },
  1440: { fast: 60, slow: 240 },
};
```

- [ ] **Step 2: Add a trailing-mean helper above the `pivot()` function**

Insert just before `function pivot(`:

```ts
// Trailing simple moving average over `values` with the given period.
// Returns an array of the same length; entries before the period is filled
// are `undefined` so Recharts renders a gap rather than a misleading point.
function trailingMean(values: number[], period: number): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(values.length);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    out[i] = i >= period - 1 ? sum / period : undefined;
  }
  return out;
}
```

- [ ] **Step 3: Type-check the file (no behavior changes yet)**

Run: `docker compose exec frontend npx tsc --noEmit`
Expected: no new errors. (The constant + helper are unused at this point — TypeScript is OK with that for top-level declarations in this codebase; if a strict-unused rule flags either, that's resolved by Task 2 which uses both.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LiveVolumePanel.tsx
git commit -m "feat(live-volume): MA period table + trailing-mean helper

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Compute totals + MAs in `pivot()`

**Files:**
- Modify: `frontend/src/components/LiveVolumePanel.tsx`

- [ ] **Step 1: Extend the `Pivoted` type and `pivot()` signature**

Find this block (around line 150–155):

```ts
type Pivoted = {
  stacked: StackRow[];
  assets: string[];
  totalUsd: number;
  currentByAsset: Record<string, number>;
};
```

Replace with:

```ts
type Pivoted = {
  stacked: StackRow[];
  assets: string[];
  totalUsd: number;
  currentByAsset: Record<string, number>;
  fastPeriod: number;
  slowPeriod: number;
  lastTotal: number | undefined;
  lastSlowMA: number | undefined;
};
```

Then change the `pivot` declaration from:

```ts
function pivot(points: RealtimeVolumePoint[]): Pivoted {
```

to:

```ts
function pivot(points: RealtimeVolumePoint[], window: number): Pivoted {
```

- [ ] **Step 2: Compute `_total` per row inside `pivot()`**

After the existing `for (const p of points) { ... }` loop, before the `const stacked = ...` line, the existing loop already accumulates per-asset values. We need to compute totals in a second pass once `stacked` is sorted, so MAs walk the rows in chronological order.

Find:

```ts
  const stacked = [...byTs.values()].sort((a, b) =>
    (a.ts as string).localeCompare(b.ts as string),
  );
```

Insert immediately AFTER it:

```ts
  // Per-row total across all assets (sum of stacked values).
  const totals: number[] = stacked.map((row) => {
    let t = 0;
    for (const a of assetSet) {
      const v = row[a];
      if (typeof v === "number") t += v;
    }
    (row as StackRow & { _total: number })._total = t;
    return t;
  });

  // MA periods come from the window selection; default to 1h's pair if the
  // caller passes an unmapped value (defensive — RANGE_OPTIONS is the only
  // source today).
  const periods = MA_PERIODS_BY_WINDOW[window] ?? MA_PERIODS_BY_WINDOW[60];
  const fastMA = trailingMean(totals, periods.fast);
  const slowMA = trailingMean(totals, periods.slow);
  for (let i = 0; i < stacked.length; i++) {
    (stacked[i] as StackRow)._fastMA = fastMA[i];
    (stacked[i] as StackRow)._slowMA = slowMA[i];
  }
```

- [ ] **Step 3: Surface the new fields in the return value**

Find the existing `return { stacked, assets: [...assetSet], totalUsd, currentByAsset };` (last line of `pivot`) and replace with:

```ts
  const lastIdx = stacked.length - 1;
  return {
    stacked,
    assets: [...assetSet],
    totalUsd,
    currentByAsset,
    fastPeriod: periods.fast,
    slowPeriod: periods.slow,
    lastTotal: lastIdx >= 0 ? totals[lastIdx] : undefined,
    lastSlowMA: lastIdx >= 0 ? slowMA[lastIdx] : undefined,
  };
```

- [ ] **Step 4: Update the `pivot()` call site to pass the window**

Find (near line 41):

```ts
  const { stacked, assets, totalUsd, currentByAsset } = useMemo(
    () => pivot(data ?? []),
    [data],
  );
```

Replace with:

```ts
  const {
    stacked,
    assets,
    totalUsd,
    currentByAsset,
    fastPeriod,
    slowPeriod,
    lastTotal,
    lastSlowMA,
  } = useMemo(() => pivot(data ?? [], minutes), [data, minutes]);
```

- [ ] **Step 5: Allow `_total | _fastMA | _slowMA` on `StackRow`**

Find the `StackRow` type (around line 27):

```ts
type StackRow = {
  ts: string;
  [k: string]: string | number | undefined;
};
```

The existing index signature already accepts `number | undefined`, so the new keys typecheck without changes. Confirm by running:

Run: `docker compose exec frontend npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/LiveVolumePanel.tsx
git commit -m "feat(live-volume): compute per-row totals and fast/slow MAs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Render MA `<Line>` overlays

**Files:**
- Modify: `frontend/src/components/LiveVolumePanel.tsx`

- [ ] **Step 1: Import `Line` from recharts**

Find:

```ts
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
```

Replace with:

```ts
import {
  Area,
  AreaChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
```

- [ ] **Step 2: Add MA color constants near the top of the file (after imports, before `RANGE_OPTIONS`)**

Insert just before `type RangeOpt = ...`:

```ts
// MA overlay colors: amber for fast (draws the eye), slate for slow (muted
// reference). Avoids the asset palette so the lines are visually distinct
// from the stacked area underneath.
const FAST_MA_COLOR = "rgb(251 191 36)"; // tailwind amber-400
const SLOW_MA_COLOR = "rgb(148 163 184)"; // tailwind slate-400
```

- [ ] **Step 3: Add the two `<Line>` elements inside `<AreaChart>` AFTER the per-asset `<Area>` block**

Find:

```tsx
                {sortedAssets.map((a) => (
                  <Area
                    key={a}
                    type="monotone"
                    dataKey={a}
                    stackId="vol"
                    stroke={rgbOf(a)}
                    fill={rgbOf(a)}
                    fillOpacity={0.65}
                  />
                ))}
              </AreaChart>
```

Replace with:

```tsx
                {sortedAssets.map((a) => (
                  <Area
                    key={a}
                    type="monotone"
                    dataKey={a}
                    stackId="vol"
                    stroke={rgbOf(a)}
                    fill={rgbOf(a)}
                    fillOpacity={0.65}
                  />
                ))}
                <Line
                  type="monotone"
                  dataKey="_fastMA"
                  stroke={FAST_MA_COLOR}
                  strokeWidth={1.5}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="_slowMA"
                  stroke={SLOW_MA_COLOR}
                  strokeWidth={1.5}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </AreaChart>
```

- [ ] **Step 4: Manual verify**

Run: `docker compose exec frontend npx tsc --noEmit`
Expected: no type errors.

Then open `http://localhost:5173`, navigate to Overview → Live on-chain volume panel, and confirm two new lines render on top of the stacked area: amber (fast) and slate-grey (slow). Toggle the window selector — both lines should redraw with new periods.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LiveVolumePanel.tsx
git commit -m "feat(live-volume): render fast/slow MA line overlays

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Tooltip labels for MA series

**Files:**
- Modify: `frontend/src/components/LiveVolumePanel.tsx`

- [ ] **Step 1: Replace the `<Tooltip>` formatter to label MA rows**

Find:

```tsx
                <Tooltip
                  contentStyle={{
                    background: "rgb(15 23 42)",
                    border: "1px solid rgb(51 65 85)",
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "rgb(148 163 184)" }}
                  formatter={(v: number) => formatUsdCompact(v)}
                />
```

Replace with:

```tsx
                <Tooltip
                  contentStyle={{
                    background: "rgb(15 23 42)",
                    border: "1px solid rgb(51 65 85)",
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "rgb(148 163 184)" }}
                  formatter={(v: number, name: string) => {
                    if (name === "_fastMA") return [formatUsdCompact(v), `${fastPeriod}m MA`];
                    if (name === "_slowMA") return [formatUsdCompact(v), `${slowPeriod}m MA`];
                    return [formatUsdCompact(v), name];
                  }}
                />
```

(`fastPeriod` and `slowPeriod` are in scope from the `useMemo` destructure added in Task 2.)

- [ ] **Step 2: Manual verify**

Reload the panel, hover the chart. Tooltip rows should include readable labels like `5m MA` and `30m MA` with the formatted USD amount. On the 24h window: `60m MA` / `240m MA`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/LiveVolumePanel.tsx
git commit -m "feat(live-volume): label MA series in tooltip

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Headline "current vs trend" tile

**Files:**
- Modify: `frontend/src/components/LiveVolumePanel.tsx`

- [ ] **Step 1: Insert the headline tile above the existing "N minutes shown" row**

Find:

```tsx
      {stacked.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-slate-500">{stacked.length} minutes shown</span>
            <span className="font-mono tabular-nums text-slate-200">
              {formatUsdCompact(totalUsd)} window total
            </span>
          </div>
          <DataAge ts={(stacked.at(-1)?.ts as string | undefined) ?? null} label="latest" />
```

Replace with:

```tsx
      {stacked.length > 0 && (
        <div className="space-y-3">
          <TrendHeadline
            lastTotal={lastTotal}
            lastSlowMA={lastSlowMA}
            slowPeriod={slowPeriod}
            rowsSoFar={stacked.length}
          />
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-slate-500">{stacked.length} minutes shown</span>
            <span className="font-mono tabular-nums text-slate-200">
              {formatUsdCompact(totalUsd)} window total
            </span>
          </div>
          <DataAge ts={(stacked.at(-1)?.ts as string | undefined) ?? null} label="latest" />
```

- [ ] **Step 2: Add the `TrendHeadline` component at the bottom of the file (after `pivot`)**

Insert at the very end of the file:

```tsx
function TrendHeadline({
  lastTotal,
  lastSlowMA,
  slowPeriod,
  rowsSoFar,
}: {
  lastTotal: number | undefined;
  lastSlowMA: number | undefined;
  slowPeriod: number;
  rowsSoFar: number;
}) {
  // Warming up: not enough samples to fill the slow window yet.
  if (lastSlowMA === undefined || lastTotal === undefined) {
    const remaining = Math.max(0, slowPeriod - rowsSoFar);
    return (
      <div className="text-xs text-slate-500">
        warming up — {slowPeriod}m baseline in {remaining}m
      </div>
    );
  }

  const delta = lastSlowMA > 0 ? lastTotal / lastSlowMA - 1 : 0;
  const absPct = Math.abs(delta) * 100;
  const flat = absPct < 5;
  const up = !flat && delta > 0;
  const down = !flat && delta < 0;
  const tint = flat ? "text-slate-500" : up ? "text-up" : "text-down";
  const arrow = flat ? "→" : up ? "▲" : "▼";
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "";
  return (
    <div className="flex items-baseline justify-between text-sm">
      <span className="font-mono tabular-nums text-slate-200">
        {formatUsdCompact(lastTotal)} / min
      </span>
      <span className={`font-mono tabular-nums ${tint}`}>
        {sign}
        {absPct.toFixed(0)}% vs {slowPeriod}m avg {arrow}
      </span>
    </div>
  );
}
```

- [ ] **Step 3: Manual verify**

Reload the panel. Verify:
- During warm-up (fewer than `slowPeriod` minutes of data): "warming up — Nm baseline in Mm" copy with countdown.
- Once warm: a row showing current $/min on the left, "+X% vs Nm avg ▲" (or `▼` / `→` flat) on the right, tinted up/down/slate.
- Toggle the window selector — `slowPeriod` in the copy updates (e.g. 30 → 240 when going 1h → 24h).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LiveVolumePanel.tsx
git commit -m "feat(live-volume): current-vs-trend headline tile

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Prepend MA rows to the legend

**Files:**
- Modify: `frontend/src/components/LiveVolumePanel.tsx`

- [ ] **Step 1: Insert two MA legend rows above the per-asset list**

Find:

```tsx
          <ul className="grid grid-cols-2 @xs:grid-cols-1 gap-x-3 gap-y-1.5 text-[11px] font-mono tabular-nums">
            {sortedAssets.slice(0, 8).map((a) => (
              <li key={a} className="flex items-center justify-between">
                <span className="flex items-center gap-2 min-w-0 truncate">
                  <span
                    className="inline-block w-2 h-2 rounded-sm shrink-0"
                    style={{ backgroundColor: rgbOf(a) }}
                  />
                  <span className="text-slate-300">{a}</span>
                </span>
                <span className="text-slate-400">
                  {formatUsdCompact(currentByAsset[a] ?? 0)}/min
                </span>
              </li>
            ))}
          </ul>
```

Replace with:

```tsx
          <ul className="grid grid-cols-2 @xs:grid-cols-1 gap-x-3 gap-y-1.5 text-[11px] font-mono tabular-nums">
            <li className="flex items-center justify-between">
              <span className="flex items-center gap-2 min-w-0 truncate">
                <span
                  className="inline-block w-2 h-2 rounded-sm shrink-0"
                  style={{ backgroundColor: FAST_MA_COLOR }}
                />
                <span className="text-slate-300">{fastPeriod}m MA</span>
              </span>
              <span className="text-slate-400">trend</span>
            </li>
            <li className="flex items-center justify-between">
              <span className="flex items-center gap-2 min-w-0 truncate">
                <span
                  className="inline-block w-2 h-2 rounded-sm shrink-0"
                  style={{ backgroundColor: SLOW_MA_COLOR }}
                />
                <span className="text-slate-300">{slowPeriod}m MA</span>
              </span>
              <span className="text-slate-400">baseline</span>
            </li>
            {sortedAssets.slice(0, 8).map((a) => (
              <li key={a} className="flex items-center justify-between">
                <span className="flex items-center gap-2 min-w-0 truncate">
                  <span
                    className="inline-block w-2 h-2 rounded-sm shrink-0"
                    style={{ backgroundColor: rgbOf(a) }}
                  />
                  <span className="text-slate-300">{a}</span>
                </span>
                <span className="text-slate-400">
                  {formatUsdCompact(currentByAsset[a] ?? 0)}/min
                </span>
              </li>
            ))}
          </ul>
```

- [ ] **Step 2: Manual verify**

Reload the panel. The legend grid should now lead with two rows ("Nm MA · trend" amber, "Mm MA · baseline" slate) followed by the existing per-asset rows. Switch windows — labels update.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/LiveVolumePanel.tsx
git commit -m "feat(live-volume): prepend MA rows to panel legend

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: End-to-end verification

**Files:**
- None to modify; verification only.

- [ ] **Step 1: Type check the whole frontend**

Run: `docker compose exec frontend npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 2: Lint the touched file**

Run: `docker compose exec frontend npx eslint src/components/LiveVolumePanel.tsx`
Expected: no errors. (Warnings about pre-existing patterns in the file are acceptable; new code shouldn't introduce any.)

- [ ] **Step 3: Production-mode build sanity**

Run: `docker compose exec frontend npm run build`
Expected: build succeeds with no new errors.

- [ ] **Step 4: Manual cross-window QA**

Open `http://localhost:5173` → Overview → Live on-chain volume.

For each of `15m`, `1h`, `4h`, `24h`:
- Two MA lines render on top of the stacked area (amber + slate). Slow line may be missing on `24h` shortly after deploy — the headline tile should show "warming up — 240m baseline in Nm" in that case.
- Tooltip rows show `{period}m MA` labels for both MA series.
- Headline tile shows either current `$X / min · ±Y% vs Nm avg ▲|▼|→` or the warming-up copy.
- Legend leads with the two MA rows then the asset rows.
- No console errors.

- [ ] **Step 5: Regression check on neighbouring panels**

Open `Stablecoin supply Δ`, `Live on-chain volume`, and any other Overview panels in the same session. Confirm:
- `StablecoinSupplyPanel` is unchanged (mint/burn rows + sparklines as before).
- The Overview grid layout still resizes correctly and no other panel throws.

- [ ] **Step 6: Final commit (if any test/lint cleanups landed in steps 1–3)**

If steps 1–3 surfaced fixes:

```bash
git add frontend/src/components/LiveVolumePanel.tsx
git commit -m "chore(live-volume): MA overlay verification cleanups

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

If no cleanups were needed, skip this step.

---

## Self-review notes

- **Spec coverage:** every spec section maps to a task — period table & helper (T1), totals + MAs (T2), Line overlays + colors (T3), tooltip labels (T4), headline tile + warm-up copy (T5), legend (T6), QA + regressions (T7). Out-of-scope items (per-asset MA, z-score, dedicated panel) are deferred per spec.
- **Placeholder scan:** no TBD/TODO. All code blocks are concrete.
- **Type consistency:** `MA_PERIODS_BY_WINDOW` introduced in T1, consumed in T2 by the same name. `FAST_MA_COLOR` / `SLOW_MA_COLOR` introduced in T3, consumed in T6 by the same names. `fastPeriod` / `slowPeriod` / `lastTotal` / `lastSlowMA` introduced as `Pivoted` fields in T2, destructured at the call site in T2 step 4, consumed in T4 (tooltip), T5 (headline), T6 (legend). `TrendHeadline` props match the values passed in T5 step 1.
