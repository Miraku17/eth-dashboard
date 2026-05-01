# Panel-Responsive Content (Container-Query Pass) — Design

**Status:** approved 2026-05-01
**Track:** UI polish (extends `2026-05-01-bento-grid-resize-design.md`)
**Related specs:**
- `2026-05-01-bento-grid-resize-design.md` (parent — added the resize layer that exposed the problem)
- `2026-05-01-customizable-layout-design.md` (root of the customization track)

## Goal

The bento-grid layer lets operators drop panels into S/M/L/Full slots
of a 4-column grid. The grid container resizes. The panels' **inner
content** doesn't — they were all built assuming full-row width. At
S/M sizes, content visibly breaks: tables overflow, stat grids wrap
awkwardly, padding overwhelms the readable area, secondary columns
crash into primary ones.

This spec adds **container-query-based** responsive layout to each
affected panel: the panel reads its own rendered width and adapts
internal layout accordingly — independent of viewport size. A panel
set to S at xl viewport (~320 px wide) and a panel sized to viewport-md
(~768 px wide) get the same Tailwind class treatment because they're
the same physical width on screen.

## Non-goals

- **Universal panel rewrite.** Only the five most pinch-sensitive
  panels get a full responsive pass in v1: WhaleTransfersPanel,
  SmartMoneyLeaderboard, AlertEventsPanel, NetworkActivityPanel,
  PriceHero. The other eight (mostly Recharts-driven) get the
  foundation (container-query wrap + Tailwind plugin) but no
  per-panel narrow-mode logic until they actually look bad in
  practice.
- **Resize handles or pixel-arbitrary widths.** Bento sizes stay at
  S / M / L / Full only.
- **Server-side responsive logic.** This is a presentation concern;
  no backend changes.
- **Mobile rework.** On `<md` viewports the bento is already
  collapsed to a single column, so panels are already full-width.
  Container queries make narrow rendering work *better* on mobile
  too as a bonus, but no separate mobile design pass.

## Why container queries (not viewport breakpoints)

Tailwind's standard `md:` / `lg:` / `xl:` breakpoints react to the
**viewport**. With bento, the same panel can be 320 px wide at one
moment (S at xl viewport) and 1280 px wide at another (Full at xl
viewport) — same viewport, different panel widths. Viewport-based
classes can't distinguish.

Container queries (`@container` + `@xs:`, `@sm:`, `@md:` …) react to
the panel's *own* rendered width. The panel knows it's narrow and
collapses its own layout regardless of where on the page it lives.

Tailwind ships a first-party plugin: `@tailwindcss/container-queries`.
~5 KB gzipped, zero runtime cost (it's CSS), supported in Tailwind 3.2+.

## Foundation: shared `<PanelShell>` wrapper

Today every panel is wrapped by `<SortablePanel>` on the Overview
(which gives it drag/resize handles) but on category pages by a local
`<Guarded>` helper. Both share an `<ErrorBoundary>` + a `<section>`.

We add a new tiny component `frontend/src/components/ui/PanelShell.tsx`
that's the canonical wrapper:

```tsx
export default function PanelShell({ children }) {
  return <div className="@container">{children}</div>;
}
```

`<SortablePanel>` and the category pages' `<Guarded>` wrap their inner
content with `<PanelShell>`. The result: every panel render site has
its content in a `@container` div. Each panel can then use `@xs:`,
`@sm:`, `@md:` Tailwind classes inside without knowing or caring about
the viewport.

This gives all 13 panels the foundation. The five targeted panels then
get per-panel adjustments.

## Container-size breakpoints

Tailwind's container-query plugin defines these breakpoints:

| Class prefix | Min container width |
|---|---|
| `@xs:` | 320 px |
| `@sm:` | 384 px |
| `@md:` | 448 px |
| `@lg:` | 512 px |
| `@xl:` | 576 px |
| `@2xl:` | 672 px |
| `@3xl:` | 768 px |

Mapping these to bento sizes (assuming a 1280 px–wide overview at xl
viewport, 24 px gaps):

- **S (¼)** → ~290 px wide → falls under `@xs` (no `@xs:` classes apply)
- **M (½)** → ~620 px → triggers `@xl` (no `@2xl:` applies)
- **L (¾)** → ~940 px → triggers `@3xl`
- **Full** → ~1280 px → all classes apply

So the practical rule of thumb for panel authors:

- `@sm:` and below = "I'm an S panel"
- `@xl:` and below = "I'm an S or M panel"
- `@3xl:` and below = "anything but Full"

We don't formalize bento-aware aliases for v1 — direct Tailwind
container-query classes are simple enough.

## Per-panel responsive passes

### 1. WhaleTransfersPanel

A multi-column tx table with: time, asset chip, amount, USD, from
address, to address, etherscan tx link.

At S/M sizes:
- Hide the **time** and **etherscan link** columns at `@xs`/`@sm`
  (visible only at `@md` and up).
- Wrap address chips beneath the amount instead of aligning columns
  at `@sm` and below.
- Drop the small "asset chip" inline color at `@xs` (visual noise
  wins over information density when there's barely room).
- The "Pending" section's column behaviour matches.

### 2. SmartMoneyLeaderboard

Today: a wide rank table with rank, address, label, realized PnL,
unrealized PnL, win rate, trade count, volume, weth bought/sold.

At S/M sizes:
- Drop secondary columns aggressively. At `@sm`: rank · address ·
  realized PnL · trade count only.
- At `@xs`: rank · address · realized PnL only.
- Convert horizontal-scrollable into vertical "card per row" at
  `@xs` (each row stacks rank, address, PnL, label as a small block).

### 3. AlertEventsPanel

Today has tabs (Events / Rules) plus a sticky "+ New rule" button +
event list with timestamp + rule name + payload preview.

At S/M sizes:
- Stack the tab strip + new-rule button vertically at `@sm` and below.
- Truncate payload preview to one line at `@xs` (today shows 2-3 lines).
- Drop the "delivered to" labels (telegram/webhook icons) at `@xs`.

### 4. NetworkActivityPanel

Today: header summary (gas price, base fee, tx count) + two charts
(gas price line, tx count bars) side-by-side.

At S/M sizes:
- Header summary's 3-column stat grid → 1-column stack at `@sm` and
  below.
- The two charts already render via Recharts `<ResponsiveContainer>`
  and don't need explicit work, but we drop the chart-title row
  height at `@xs` to reclaim vertical space.

### 5. PriceHero

Today: large price big-number + 24h change chip + low/high range bar
+ sparkline, in a 2-column flex layout (`flex-col lg:flex-row`).

At S/M sizes:
- Today the responsive break is at `lg:` (viewport-1024 px) — switch
  to `@2xl:flex-row` (container-672 px). Now: vertical stack at S/M,
  horizontal at L/Full.
- At `@xs`: drop the "Mainnet" subtitle, hide the secondary "ETH"
  badge, slim down the EthGlyph icon size from 12 to 9.
- Range bar's "Low / High" labels collapse to numbers only at `@xs`.

### 6. The other eight panels (foundation only)

`<PanelShell>` wraps them. No per-panel narrow-mode classes added.
They render via Recharts `<ResponsiveContainer>` which auto-fits;
secondary text might cramp slightly at S/M but doesn't break.

If a particular panel proves uncomfortable in real use, future
follow-ups can add narrow-mode passes one panel at a time. The
foundation is in place.

## Architecture

### File changes

```
frontend/
  package.json                                # ADD: @tailwindcss/container-queries
  tailwind.config.js                          # ADD: plugin import + registration
  src/components/
    ui/PanelShell.tsx                         # NEW — the @container wrapper
    ui/SortablePanel.tsx                      # MODIFIED — wrap children in <PanelShell>
  src/routes/
    OverviewPage.tsx                          # No change (uses SortablePanel)
    MarketsPage.tsx                           # MODIFIED — Guarded wraps with PanelShell
    OnchainPage.tsx                           # MODIFIED — same
    MempoolPage.tsx                           # MODIFIED — same
  src/components/
    WhaleTransfersPanel.tsx                   # MODIFIED — narrow-mode pass
    SmartMoneyLeaderboard.tsx                 # MODIFIED — narrow-mode pass
    AlertEventsPanel.tsx                      # MODIFIED — narrow-mode pass
    NetworkActivityPanel.tsx                  # MODIFIED — narrow-mode pass
    PriceHero.tsx                             # MODIFIED — narrow-mode pass
```

No new state, no store changes, no backend changes, no env vars.

### Tailwind plugin wiring

`frontend/tailwind.config.js` becomes:

```javascript
import containerQueries from "@tailwindcss/container-queries";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: { /* unchanged */ } },
  plugins: [containerQueries],
};
```

Vite's tailwind pipeline picks up the plugin automatically; no
PostCSS config changes needed.

### `<PanelShell>` minimal definition

```tsx
import type { ReactNode } from "react";

type Props = { children: ReactNode };

/**
 * Panel content wrapper that establishes a container-query context.
 * Inner Tailwind classes can use `@xs:`, `@sm:`, `@md:` etc. and they
 * trigger off this element's rendered width — independent of viewport.
 */
export default function PanelShell({ children }: Props) {
  return <div className="@container w-full">{children}</div>;
}
```

The `w-full` is needed because `@container` doesn't itself imply any
sizing — without `w-full` the wrapper would size to its content and
the container-query breakpoints would activate based on content
width rather than allotted column width.

### `<SortablePanel>` integration

The current return:

```tsx
<section ref={setNodeRef} ... className={`scroll-mt-20 relative ${SPAN_CLASS[width]}`}>
  {/* edit-mode handles */}
  <ErrorBoundary label={label}>{children}</ErrorBoundary>
</section>
```

becomes:

```tsx
<section ref={setNodeRef} ... className={`scroll-mt-20 relative ${SPAN_CLASS[width]}`}>
  {/* edit-mode handles */}
  <ErrorBoundary label={label}>
    <PanelShell>{children}</PanelShell>
  </ErrorBoundary>
</section>
```

### Category pages' `<Guarded>` integration

Each category page (MarketsPage / OnchainPage / MempoolPage) defines a
local `<Guarded>` helper. Each one's body wraps `children` in
`<PanelShell>` between `<ErrorBoundary>` and the actual children:

```tsx
function Guarded({ label, children, id }) {
  return (
    <section id={id} className="scroll-mt-20">
      <ErrorBoundary label={label}>
        <PanelShell>{children}</PanelShell>
      </ErrorBoundary>
    </section>
  );
}
```

(Same change applied identically across all three category pages.)

### Per-panel narrow-mode pass: an example sketch

Today's `WhaleTransfersPanel` table row:

```tsx
<tr>
  <td>{formatTime(t.ts)}</td>
  <td><AssetChip asset={t.asset} /></td>
  <td>{formatAmount(t.amount)}</td>
  <td>{formatUsd(t.usd_value)}</td>
  <td><AddressLink address={t.from_addr} label={t.from_label} /></td>
  <td><AddressLink address={t.to_addr} label={t.to_label} /></td>
  <td><a href={etherscanUrl(t.tx_hash)}>↗</a></td>
</tr>
```

After the pass — using container-query classes to hide secondary
columns:

```tsx
<tr>
  <td className="hidden @md:table-cell">{formatTime(t.ts)}</td>
  <td className="hidden @xs:table-cell"><AssetChip asset={t.asset} /></td>
  <td>{formatAmount(t.amount)}</td>
  <td>{formatUsd(t.usd_value)}</td>
  <td><AddressLink address={t.from_addr} label={t.from_label} /></td>
  <td><AddressLink address={t.to_addr} label={t.to_label} /></td>
  <td className="hidden @md:table-cell"><a href={etherscanUrl(t.tx_hash)}>↗</a></td>
</tr>
```

Plus matching `<th>` `hidden @md:table-cell` etc. for the header.

## Edge cases

- **Recharts `<ResponsiveContainer>` and `@container`.** Recharts measures the
  parent ResizeObserver. With container queries it still works — the
  observer reports the actual rendered size. No conflict.
- **Lightweight Charts and `@container`.** PriceChart attaches a
  `window.resize` listener and calls `chart.applyOptions({ width: containerRef.current.clientWidth })`.
  This is viewport-driven, not panel-driven. **For v1 this is fine** —
  the chart's own resize is good enough at S/M because lightweight-charts
  internally resamples cleanly. If we later see issues, we'd swap the
  resize listener for a `ResizeObserver` on the panel's wrapper. Not
  in scope for this spec.
- **Edit-mode handle cluster.** The S/M/L/Full + drag + remove buttons
  in `<SortablePanel>`'s top-right are absolute-positioned, outside
  `<PanelShell>`. They don't get `@container` treatment and continue
  rendering at their fixed pixel size regardless of panel width.
- **Existing viewport breakpoints inside panels.** Panels today use
  `md:` / `lg:` / `xl:` for layout. We keep those for cases where
  viewport-driven choices are still right (e.g. mobile-only hiding).
  Container-query classes (`@xs:`, `@sm:`) only get added where panel-
  width is the right axis. The two coexist.
- **Tailwind purging.** Container-query classes (`@xs:hidden`,
  `@md:table-cell`, etc.) are literal strings in source, so Tailwind's
  Just-In-Time engine sees them at build time. No safelist needed.
- **Tab-content shift at the breakpoint.** When a user drags-resizes
  a panel from M to S, the table columns disappear with a hard
  toggle (no transition). Acceptable for v1; smoothing it would be
  a much larger CSS-transition pass.

## Tests

Frontend has no vitest. Validation = `npm run build` + a manual smoke
checklist that covers the five targeted panels at all four widths.

The smoke checklist is a per-panel grid:

| Panel | Width S | Width M | Width L | Width Full |
|---|---|---|---|---|
| WhaleTransfersPanel | Time + etherscan-link cols hidden; addresses readable | Time/link visible; some columns may wrap | Full table | Full table |
| SmartMoneyLeaderboard | Rank + address + realized-PnL only | Adds trade count column | Most columns | All columns |
| AlertEventsPanel | Tabs + new-rule stacked vertically; payload one-line | Same as L | Side-by-side | Side-by-side |
| NetworkActivityPanel | Stat grid stacked vertically | Same as S | Stat grid horizontal | Same as L |
| PriceHero | Big number above sparkline (vertical) | Vertical | Side-by-side | Side-by-side |

All performed in a single browser session; reset to default in
between if the bento layout drifts.

## Implementation milestones

(Refined in the writing-plans pass.)

1. Install `@tailwindcss/container-queries`. Wire into `tailwind.config.js`.
2. Create `<PanelShell>`. Wrap `<SortablePanel>`'s children in it.
3. Wrap the three category pages' `<Guarded>` helpers in `<PanelShell>`.
4. WhaleTransfersPanel narrow-mode pass.
5. SmartMoneyLeaderboard narrow-mode pass.
6. AlertEventsPanel narrow-mode pass.
7. NetworkActivityPanel narrow-mode pass.
8. PriceHero narrow-mode pass.
9. CLAUDE.md note + manual smoke.

## Risks and known limits

- **Visual regressions in untested width permutations.** Operators may
  set a panel to a width we didn't explicitly test (e.g. drag-resize
  M → S → L). Container-query CSS handles this naturally at runtime,
  but there's no test coverage. Mitigation: the smoke checklist tests
  all 4 sizes per touched panel; visual regressions are quick to spot.
- **The other 8 panels at S/M.** They get the foundation only. Some
  may still look pinched. We accept that for v1 and add narrow-mode
  passes follow-up if real use surfaces specific pinches.
- **Plugin upgrade footprint.** `@tailwindcss/container-queries` is a
  first-party plugin maintained by the Tailwind team. Low maintenance
  risk.
- **Lightweight Charts viewport-resize coupling** (described above).
  Not actually broken for v1; flagged for future.

## Future work (not v1)

- Narrow-mode passes for the other 8 panels as needed.
- Replace PriceChart's window.resize listener with a panel-scoped
  ResizeObserver so lightweight-charts reflows on bento resize too.
- Smooth transitions between width states (column show/hide
  animation, padding interpolation).
- Bento-aware Tailwind aliases (`@bento-s`, `@bento-m`, etc.) if
  authoring-time mental model proves clunky.
