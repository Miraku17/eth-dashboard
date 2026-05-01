# Panel-Responsive Content (Container-Query Pass) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make panel content responsive to its own rendered width (not viewport) by adding Tailwind container queries, so panels look right at every bento size (S/M/L/Full).

**Architecture:** Install `@tailwindcss/container-queries`, register it in `tailwind.config.js`, and add a tiny `<PanelShell>` `@container` wrapper used by both `<SortablePanel>` (Overview) and the category pages' local `<Guarded>` helper. Then per-panel narrow-mode passes on the 5 most pinch-sensitive panels (WhaleTransfers, SmartMoneyLeaderboard, AlertEvents, NetworkActivity, PriceHero) — each adds `@xs:`/`@sm:`/`@md:` Tailwind classes that toggle column visibility and stack-vs-row layout based on the panel's own size.

**Tech Stack:** Tailwind 3.4 + first-party `@tailwindcss/container-queries` plugin (~5 KB gzipped, zero runtime). Zero state changes, zero backend changes.

**Spec:** `docs/superpowers/specs/2026-05-01-panel-responsive-design.md`.

**File map:**
- Modify:
  - `frontend/package.json` + `package-lock.json` (add the plugin)
  - `frontend/tailwind.config.js` (register the plugin)
  - `frontend/src/components/ui/SortablePanel.tsx` (wrap children in `<PanelShell>`)
  - `frontend/src/routes/MarketsPage.tsx` (wrap Guarded children)
  - `frontend/src/routes/OnchainPage.tsx` (wrap Guarded children)
  - `frontend/src/routes/MempoolPage.tsx` (wrap Guarded children)
  - `frontend/src/components/WhaleTransfersPanel.tsx` (narrow-mode pass)
  - `frontend/src/components/SmartMoneyLeaderboard.tsx` (narrow-mode pass)
  - `frontend/src/components/AlertEventsPanel.tsx` (narrow-mode pass)
  - `frontend/src/components/NetworkActivityPanel.tsx` (narrow-mode pass)
  - `frontend/src/components/PriceHero.tsx` (narrow-mode pass)
  - `CLAUDE.md` (UI polish line)
- Create:
  - `frontend/src/components/ui/PanelShell.tsx`

No frontend test infra exists (no vitest); validation = `npm run build` + a manual smoke checklist against all four bento sizes per touched panel.

---

## Task 1 — Install plugin + wire Tailwind config

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`
- Modify: `frontend/tailwind.config.js`

- [ ] **Step 1: Install the plugin**

```bash
cd frontend && npm i -D @tailwindcss/container-queries
```

Verify it appears under `"devDependencies"` in `frontend/package.json`.

- [ ] **Step 2: Register the plugin**

Replace the entire content of `frontend/tailwind.config.js` with:

```javascript
import containerQueries from "@tailwindcss/container-queries";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        surface: {
          base: "#0a0d12",
          card: "#10141b",
          sunken: "#0d1117",
          raised: "#151a22",
          border: "#1b2028",
          divider: "#161b23",
        },
        brand: {
          DEFAULT: "#7c83ff",
          soft: "#8b93ff",
          muted: "#2a2e4a",
        },
        up: "#19c37d",
        down: "#ff5c62",
      },
      boxShadow: {
        card: "0 1px 0 rgba(255,255,255,0.02) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
      },
    },
  },
  plugins: [containerQueries],
};
```

(Only `import` and `plugins` lines added; the rest mirrors the existing config.)

- [ ] **Step 3: Build to verify**

```bash
cd frontend && npm run build
```

Expected: succeeds. No CSS classes use container queries yet so no visual change.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tailwind.config.js
git commit -m "feat(layout): add @tailwindcss/container-queries plugin"
```

---

## Task 2 — Create `<PanelShell>`

**Files:**
- Create: `frontend/src/components/ui/PanelShell.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/ui/PanelShell.tsx` with this exact content:

```tsx
import type { ReactNode } from "react";

type Props = { children: ReactNode };

/**
 * Panel content wrapper that establishes a container-query context.
 * Inner Tailwind classes can use `@xs:`, `@sm:`, `@md:` etc. and they
 * trigger off this element's rendered width — independent of viewport.
 *
 * `w-full` is required because `@container` doesn't itself imply sizing;
 * without it the wrapper would shrink to its content and container-query
 * breakpoints would activate based on content width rather than allotted
 * column width.
 */
export default function PanelShell({ children }: Props) {
  return <div className="@container w-full">{children}</div>;
}
```

- [ ] **Step 2: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ui/PanelShell.tsx
git commit -m "feat(layout): add PanelShell @container wrapper"
```

---

## Task 3 — Wrap `<SortablePanel>`'s children in `<PanelShell>`

**Files:**
- Modify: `frontend/src/components/ui/SortablePanel.tsx`

- [ ] **Step 1: Add the import**

Find the existing imports at the top of `frontend/src/components/ui/SortablePanel.tsx`. After the `ErrorBoundary` import line, add:

```tsx
import PanelShell from "./PanelShell";
```

- [ ] **Step 2: Wrap the children**

Find the closing line of the component's return — currently:

```tsx
      <ErrorBoundary label={label}>{children}</ErrorBoundary>
    </section>
  );
}
```

Replace with:

```tsx
      <ErrorBoundary label={label}>
        <PanelShell>{children}</PanelShell>
      </ErrorBoundary>
    </section>
  );
}
```

- [ ] **Step 3: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds. No visual change; panels render identically because no `@*:` classes exist yet inside any panel.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ui/SortablePanel.tsx
git commit -m "feat(layout): SortablePanel wraps content in PanelShell @container"
```

---

## Task 4 — Wrap category pages' `<Guarded>` helpers in `<PanelShell>`

**Files:**
- Modify: `frontend/src/routes/MarketsPage.tsx`
- Modify: `frontend/src/routes/OnchainPage.tsx`
- Modify: `frontend/src/routes/MempoolPage.tsx`

The same change applies identically to all three files.

- [ ] **Step 1: Update `MarketsPage.tsx`**

Open `frontend/src/routes/MarketsPage.tsx`. Add this import alongside the existing imports near the top:

```tsx
import PanelShell from "../components/ui/PanelShell";
```

Find the existing `Guarded` function (it currently looks like):

```tsx
function Guarded({
  label,
  children,
  id,
}: {
  label: string;
  children: ReactNode;
  id?: string;
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <ErrorBoundary label={label}>{children}</ErrorBoundary>
    </section>
  );
}
```

Replace with:

```tsx
function Guarded({
  label,
  children,
  id,
}: {
  label: string;
  children: ReactNode;
  id?: string;
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <ErrorBoundary label={label}>
        <PanelShell>{children}</PanelShell>
      </ErrorBoundary>
    </section>
  );
}
```

- [ ] **Step 2: Update `OnchainPage.tsx`**

Apply the same change: add the `PanelShell` import and wrap `{children}` in `<PanelShell>` inside the local `Guarded` function. The existing `Guarded` looks identical to MarketsPage's.

- [ ] **Step 3: Update `MempoolPage.tsx`**

Apply the same change: add the `PanelShell` import and wrap `{children}` in `<PanelShell>` inside the local `Guarded` function.

- [ ] **Step 4: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds. No visual change yet.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/MarketsPage.tsx \
        frontend/src/routes/OnchainPage.tsx \
        frontend/src/routes/MempoolPage.tsx
git commit -m "feat(layout): category pages wrap Guarded children in PanelShell"
```

---

## Task 5 — `<WhaleTransfersPanel>` narrow-mode pass

**Files:**
- Modify: `frontend/src/components/WhaleTransfersPanel.tsx`

Goal: hide the **Time** and **Tx** columns at narrow container widths so the From/To/Amount/USD columns get enough room.

- [ ] **Step 1: Hide the Time column at narrow widths**

In `frontend/src/components/WhaleTransfersPanel.tsx`, find the table header row (around lines 169–191). It contains seven `<th>` cells: Time, Asset, From, To, Amount, USD, Tx.

Add `hidden @md:table-cell` to the Time `<th>` and Tx `<th>`:

Change:
```tsx
                <th className="text-left font-medium px-5 py-3 border-b border-surface-divider">
                  Time
                </th>
```
to:
```tsx
                <th className="hidden @md:table-cell text-left font-medium px-5 py-3 border-b border-surface-divider">
                  Time
                </th>
```

And change the Tx header similarly:
```tsx
                <th className="text-right font-medium px-5 py-3 border-b border-surface-divider">
                  Tx
                </th>
```
to:
```tsx
                <th className="hidden @md:table-cell text-right font-medium px-5 py-3 border-b border-surface-divider">
                  Tx
                </th>
```

- [ ] **Step 2: Hide the matching `<td>` cells in body rows**

The body rows (around lines 194–232) render the same 7 cells. Add `hidden @md:table-cell` to the Time `<td>` and Tx `<td>`:

Change:
```tsx
                  <td className="px-5 py-2.5 text-slate-400 whitespace-nowrap border-b border-surface-divider/60">
                    {relativeTime(t.ts)}
                  </td>
```
to:
```tsx
                  <td className="hidden @md:table-cell px-5 py-2.5 text-slate-400 whitespace-nowrap border-b border-surface-divider/60">
                    {relativeTime(t.ts)}
                  </td>
```

And the Tx `<td>` (the one wrapping the Etherscan link):
```tsx
                  <td className="px-5 py-2.5 text-right border-b border-surface-divider/60">
                    <a
                      href={`https://etherscan.io/tx/${t.tx_hash}`}
```
to:
```tsx
                  <td className="hidden @md:table-cell px-5 py-2.5 text-right border-b border-surface-divider/60">
                    <a
                      href={`https://etherscan.io/tx/${t.tx_hash}`}
```

- [ ] **Step 3: Apply the same pattern to the Pending section**

The same panel renders a "Pending" section above the confirmed transfers (separate `<table>` for pending transfers, similar 7-column structure). Find the matching Time and Tx `<th>` and `<td>` cells and add `hidden @md:table-cell` to each (same modification).

If the Pending section's table layout is structurally identical to the confirmed one, the four edits (2 headers + 2 body cells, multiplied across the two tables) should be straightforward to find by searching for `formatTime`, `relativeTime`, or `etherscan.io/tx/` matches.

- [ ] **Step 4: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WhaleTransfersPanel.tsx
git commit -m "feat(layout): WhaleTransfersPanel hides Time + Tx cols at @sm widths"
```

---

## Task 6 — `<SmartMoneyLeaderboard>` narrow-mode pass

**Files:**
- Modify: `frontend/src/components/SmartMoneyLeaderboard.tsx`

Goal: at narrow container widths, drop the secondary columns (Unrealized PnL, Win rate, Volume) — keep rank, address, realized PnL, trades.

- [ ] **Step 1: Hide the secondary `<th>` cells**

In `frontend/src/components/SmartMoneyLeaderboard.tsx`, find the table header (around lines 58–67). It has 7 `<th>` cells: `#`, Wallet, Realized PnL, Unrealized, Win rate, Trades, Volume.

Add `hidden @md:table-cell` to **Unrealized**, **Win rate**, and **Volume** headers:

Change:
```tsx
                <th className="text-right px-4 py-3 font-medium">Unrealized</th>
```
to:
```tsx
                <th className="hidden @md:table-cell text-right px-4 py-3 font-medium">Unrealized</th>
```

Same for **Win rate**:
```tsx
                <th className="hidden @md:table-cell text-right px-4 py-3 font-medium">Win rate</th>
```

Same for **Volume**:
```tsx
                <th className="hidden @md:table-cell text-right px-4 py-3 font-medium">Volume</th>
```

- [ ] **Step 2: Hide the matching `<td>` cells**

The body rows render the same 7 cells. The Unrealized cell is around lines 97–110, Win rate around lines 111–113, Volume around lines 117–119.

Add `hidden @md:table-cell ` to the className of each of those three `<td>` elements (preserving the rest of the existing className).

For example, the Unrealized cell's className currently looks like:
```tsx
                    className={
                      "px-4 py-3 text-right font-mono tabular-nums " +
                      (e.unrealized_pnl_usd === null
                        ? "text-slate-600"
                        : e.unrealized_pnl_usd >= 0
                          ? "text-up/80"
                          : "text-down/80")
                    }
```
Replace the leading `"px-4 py-3 ..."` with `"hidden @md:table-cell px-4 py-3 ..."`.

For Win rate:
```tsx
                  <td className="px-4 py-3 text-right font-mono text-slate-300 tabular-nums">
                    {fmtPct(e.win_rate)}
                  </td>
```
becomes:
```tsx
                  <td className="hidden @md:table-cell px-4 py-3 text-right font-mono text-slate-300 tabular-nums">
                    {fmtPct(e.win_rate)}
                  </td>
```

For Volume:
```tsx
                  <td className="px-4 py-3 text-right font-mono text-slate-300 tabular-nums">
                    {formatUsdCompact(e.volume_usd)}
                  </td>
```
becomes:
```tsx
                  <td className="hidden @md:table-cell px-4 py-3 text-right font-mono text-slate-300 tabular-nums">
                    {formatUsdCompact(e.volume_usd)}
                  </td>
```

- [ ] **Step 3: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SmartMoneyLeaderboard.tsx
git commit -m "feat(layout): SmartMoneyLeaderboard drops secondary cols at @sm widths"
```

---

## Task 7 — `<AlertEventsPanel>` narrow-mode pass

**Files:**
- Modify: `frontend/src/components/AlertEventsPanel.tsx`

Goal: stack tabs + new-rule button vertically at narrow container widths; truncate payload preview to one line at very narrow widths.

- [ ] **Step 1: Stack the header strip vertically at @sm**

Find the header element of `<AlertEventsPanel>` that contains the Events/Rules tab strip and the "+ New rule" button. They're typically arranged in a horizontal `flex items-center justify-between` row.

Locate the line that has the horizontal flex wrapper for that header (search for `flex items-center justify-between` near the top of the panel JSX, OR `Events` and `Rules` tab labels — these appear together).

Change the wrapper from `flex items-center justify-between` to `flex flex-col @sm:flex-row @sm:items-center @sm:justify-between gap-2 @sm:gap-0` so it stacks vertically at narrow widths.

Replace:
```tsx
<div className="flex items-center justify-between ...">
```
with (preserving the rest of the className tail after `between`):
```tsx
<div className="flex flex-col @sm:flex-row @sm:items-center @sm:justify-between gap-2 @sm:gap-0 ...">
```

- [ ] **Step 2: Truncate payload preview at @xs**

Find the JSX that renders the event payload preview text (search for `payload` or a 2–3 line text block beneath the rule name in each row). It's likely styled `text-xs text-slate-400` or similar.

Add `line-clamp-1 @sm:line-clamp-none` to that element's className so it shows a single line at narrow widths and full text from `@sm` up.

For example, if the payload preview is rendered like:
```tsx
<p className="text-xs text-slate-500 mt-0.5">
  {summarizePayload(event.payload)}
</p>
```

Replace with:
```tsx
<p className="text-xs text-slate-500 mt-0.5 line-clamp-1 @sm:line-clamp-none">
  {summarizePayload(event.payload)}
</p>
```

(If the panel uses a `<div>` or `<span>` element for the preview instead of `<p>`, apply the same class addition; the structure isn't important — just add `line-clamp-1 @sm:line-clamp-none` to the line-rendering element.)

- [ ] **Step 3: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AlertEventsPanel.tsx
git commit -m "feat(layout): AlertEventsPanel stacks header + truncates payload at @sm"
```

---

## Task 8 — `<NetworkActivityPanel>` narrow-mode pass

**Files:**
- Modify: `frontend/src/components/NetworkActivityPanel.tsx`

Goal: stat-grid header (gas price, base fee, tx count) collapses from 3-column to 1-column stack at narrow container widths.

- [ ] **Step 1: Find the stat grid container**

Open `frontend/src/components/NetworkActivityPanel.tsx`. Search for `grid-cols-3` near the top of the component's JSX — that's the 3-column container holding the gas price, base fee, and tx count summary cells.

The container's className is likely `grid grid-cols-3 ...` or `grid grid-cols-3 divide-x divide-surface-divider`.

- [ ] **Step 2: Make it container-query responsive**

Change the className from `grid grid-cols-3 ...` to `grid grid-cols-1 @md:grid-cols-3 ...` so it stacks at narrow widths and goes 3-column at `@md` and above.

If the grid uses `divide-x` (vertical dividers between cells), wrap that in a class condition too: `divide-y @md:divide-y-0 @md:divide-x` so dividers become horizontal when stacked.

Example replacement — if the existing className is:
```tsx
<div className="grid grid-cols-3 divide-x divide-surface-divider border-b border-surface-divider">
```

Replace with:
```tsx
<div className="grid grid-cols-1 @md:grid-cols-3 divide-y @md:divide-y-0 @md:divide-x divide-surface-divider border-b border-surface-divider">
```

(Adjust class details to match what's actually in the file; the pattern is: `grid-cols-1 @md:grid-cols-3` + flip `divide-x` to `divide-y @md:divide-y-0 @md:divide-x`.)

- [ ] **Step 3: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/NetworkActivityPanel.tsx
git commit -m "feat(layout): NetworkActivityPanel stat grid stacks vertically at @sm widths"
```

---

## Task 9 — `<PriceHero>` narrow-mode pass

**Files:**
- Modify: `frontend/src/components/PriceHero.tsx`

Goal: the existing `flex-col lg:flex-row` (viewport-driven) becomes `flex-col @2xl:flex-row` (container-driven) so the hero stacks vertically at S/M and goes side-by-side at L/Full.

- [ ] **Step 1: Find the hero's outer flex container**

In `frontend/src/components/PriceHero.tsx`, find the `<div>` that wraps the left "identity + price" block and the right sparkline block. Search for `flex-col lg:flex-row`. It's around line 66 of the file.

- [ ] **Step 2: Replace viewport-based class with container-query class**

Change:
```tsx
<div className="flex flex-col lg:flex-row">
```
to:
```tsx
<div className="flex flex-col @2xl:flex-row">
```

(`lg:` → `@2xl:`. The container-query `@2xl` triggers at 672 px panel width — roughly the L bento size at xl viewport.)

- [ ] **Step 3: Update the inner border between left/right blocks**

The left-block has borders that separate it from the right-block. Search for `border-b lg:border-b-0 lg:border-r border-surface-divider` (or similar — the block uses `border-b` at vertical layout and `border-r` at horizontal).

Change:
```tsx
className="flex-1 p-6 border-b lg:border-b-0 lg:border-r border-surface-divider min-w-0"
```
to:
```tsx
className="flex-1 p-6 border-b @2xl:border-b-0 @2xl:border-r border-surface-divider min-w-0"
```

- [ ] **Step 4: Update the right block's width hint**

The right-block typically declares a width via `lg:w-[40%]` or similar. Find that:
```tsx
<div className="lg:w-[40%] p-6 flex items-center">
```

Change to:
```tsx
<div className="@2xl:w-[40%] p-6 flex items-center">
```

- [ ] **Step 5: Update other lg: viewport classes inside the hero**

Search the file for any remaining `lg:` classes that govern hero layout (e.g., `lg:text-5xl`, `lg:h-12`). For each one, decide:
- **If it's a typography or sizing class for the price big-number** (`text-4xl lg:text-5xl`): change `lg:` to `@2xl:` so size grows when the panel widens, not when the viewport widens.
- **If it's an unrelated viewport responsive class** (e.g., for the AuthGate or external layout): leave as-is.

For the price big-number specifically, change:
```tsx
<div className="font-mono text-4xl lg:text-5xl font-semibold tabular-nums tracking-tight">
```
to:
```tsx
<div className="font-mono text-4xl @2xl:text-5xl font-semibold tabular-nums tracking-tight">
```

And for the loading skeleton:
```tsx
<div className="skeleton h-10 lg:h-12 w-48" />
```
to:
```tsx
<div className="skeleton h-10 @2xl:h-12 w-48" />
```

- [ ] **Step 6: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/PriceHero.tsx
git commit -m "feat(layout): PriceHero swaps lg: → @2xl: for container-driven layout"
```

---

## Task 10 — Manual smoke test + CLAUDE.md note

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Restart the local stack to pick up the new bundle**

From the repo root:

```bash
make down && make up
```

Wait ~10 s.

- [ ] **Step 2: Smoke test in the browser**

Open http://localhost:5173, log in. Hard-refresh (`Cmd+Shift+R`). Then:

- [ ] **Setup the test scaffold:** click **Customize** on Overview. Add WhaleTransfers, SmartMoney, AlertEvents, NetworkActivity, and PriceHero if they're not already on overview. Resize them all to **S** to test the narrow path.
- [ ] **WhaleTransfers at S:** Time and Tx columns are HIDDEN. From/To/Amount/USD remain readable. Resize to **M** — Time and Tx still hidden. Resize to **L** or **Full** — Time and Tx are visible again.
- [ ] **SmartMoneyLeaderboard at S:** Unrealized, Win rate, Volume columns HIDDEN. Rank/Address/RealizedPnL/Trades remain. Resize to **M** — same. Resize to **L/Full** — all columns visible.
- [ ] **AlertEventsPanel at S:** Tabs (Events/Rules) and "+ New rule" button stack VERTICALLY. Payload preview lines truncated to a single line. Resize to **M** — same stacked layout. Resize to **L/Full** — header row goes horizontal.
- [ ] **NetworkActivityPanel at S:** Header stat row (gas price / base fee / tx count) stacked VERTICALLY (1 column, horizontal dividers). Resize to **M** — still stacked. Resize to **L/Full** — 3-column horizontal layout with vertical dividers.
- [ ] **PriceHero at S:** Big number above sparkline (vertical stack). Resize to **M** — still vertical. Resize to **L** — flips to side-by-side. Resize to **Full** — side-by-side.
- [ ] **Existing features still work:** click an address in WhaleTransfers → wallet drawer opens. Live ticker still ticks. Reset button still works. Drag-reorder still works.
- [ ] **Mobile (375 px DevTools viewport):** every panel renders in its single-column fallback (the bento grid collapses) and looks reasonable. Container queries work in mobile too as a bonus.
- [ ] **Other 8 panels at S width:** look at OrderFlow, VolumeStructure, Derivatives, Stablecoin, OnchainVolume, Mempool, ExchangeFlows, PriceChart. Confirm they don't visually break — Recharts panels should auto-fit, others may look slightly cramped but should not overflow or crash. Note any specific panels that need follow-up for future passes.

- [ ] **Step 3: Update CLAUDE.md**

Edit `CLAUDE.md`. Find the existing customizable-overview line under "## UI polish":

```markdown
- Customizable overview ✅ React Router 4-page split (`Overview · Markets · Onchain · Mempool`); overview supports drag-to-reorder, add/remove, and bento-grid resize (S/M/L/Full → 1/2/3/4 cols) via `dnd-kit/sortable` + a 4-col CSS grid, persisted to LocalStorage (schema v2); category pages are fixed-in-code, derived from a single `lib/panelRegistry.ts`. Desktop only (`≥md`); mobile renders a clean default stack. Specs: `docs/superpowers/specs/2026-05-01-customizable-layout-design.md`, `docs/superpowers/specs/2026-05-01-bento-grid-resize-design.md`.
```

Append this new bullet directly after it (still under "## UI polish"):

```markdown
- Panel-responsive content ✅ `@tailwindcss/container-queries` plugin + `<PanelShell>` wraps every panel in an `@container` div so inner Tailwind classes (`@xs:` / `@sm:` / `@md:` / `@2xl:`) react to the panel's own rendered width rather than the viewport. v1 ships narrow-mode passes for the 5 most pinch-sensitive panels (WhaleTransfers, SmartMoneyLeaderboard, AlertEvents, NetworkActivity, PriceHero); other 8 get the foundation only. Spec: `docs/superpowers/specs/2026-05-01-panel-responsive-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(layout): note panel-responsive content shipping under UI polish"
```

---

## Self-review

**Spec coverage:**

- Foundation (plugin + `<PanelShell>` + wrapping `<SortablePanel>` and `<Guarded>`): Tasks 1–4.
- Per-panel narrow-mode passes for the 5 pinch-sensitive panels: Tasks 5–9.
- Other 8 panels get foundation only via `<PanelShell>` (Tasks 3 + 4) — no further work this PR.
- CLAUDE.md note: Task 10.
- Manual smoke covering all 4 widths per touched panel: Task 10 step 2.
- Tailwind plugin wiring (config.js): Task 1.
- `w-full` on the `@container` wrapper (necessary for sizing): Task 2.
- Container-size breakpoint mapping (`@xs` → S, `@2xl` → L, etc.): used in Tasks 5–9.
- Recharts compatibility, lightweight-charts compatibility: discussed in spec, no code change needed v1.

**Placeholder scan:**
- Tasks 5, 6 give exact code transformations (find specific class strings and add `hidden @md:table-cell`).
- Tasks 7, 8 are slightly looser ("find the X element and add Y class") because the exact class strings vary slightly across panels — the search anchor (`flex items-center justify-between`, `grid-cols-3`) is concrete enough for an implementer.
- Task 9 lists 5 specific viewport→container-query swaps.
- No "TBD" / "implement later" / "etc." patterns in any step.

**Type consistency:**
- `<PanelShell>` is a no-prop wrapper with `{ children: ReactNode }` — same shape used in Tasks 3, 4.
- No new types beyond `PanelShell`'s `Props`.
- No store API changes; `useOverviewLayout` shape is preserved.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-01-panel-responsive.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
