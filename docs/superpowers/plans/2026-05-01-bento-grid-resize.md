# Bento-grid Resize for Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-panel column-span sizing (S/M/L/Full → 1/2/3/4 cols of a 4-col CSS grid) to the customizable Overview, with size buttons inside the existing edit-mode handle cluster.

**Architecture:** Bump the registry to carry `defaultWidth` per panel. Bump the LocalStorage schema to v2 so each entry stores `{ id, width }` instead of just an id; migrate v1 → v2 by reading each panel's `defaultWidth`. Replace the Overview's flat vertical stack with a responsive 4-col CSS grid. Each `<SortablePanel>` applies a static `SPAN_CLASS[width]` literal (Tailwind-purge friendly) and renders an in-cluster `<SizeButtons>` row in edit mode that calls `resize(id, width)` on the store.

**Tech Stack:** TypeScript, React, Tailwind CSS (already installed), Zustand persist middleware (already installed). Zero new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-01-bento-grid-resize-design.md`.

**File map:**
- Modify:
  - `frontend/src/lib/panelRegistry.ts` (add `PanelWidth` type, `defaultWidth` field per panel, change shape of `DEFAULT_OVERVIEW_LAYOUT`)
  - `frontend/src/state/overviewLayout.ts` (schema v2, replace `panelIds` with `panels`, add `resize`, rewrite `migrate` for v1 → v2)
  - `frontend/src/components/ui/SortablePanel.tsx` (accept `width` prop, apply `SPAN_CLASS[width]`, embed `<SizeButtons>` in edit-mode cluster)
  - `frontend/src/components/ui/AddPanelTile.tsx` (read `panels.find(...)` instead of `panelIds.includes(...)`)
  - `frontend/src/routes/OverviewPage.tsx` (4-col grid container, iterate over `panels` not `panelIds`, pass `width`)
  - `CLAUDE.md` (append "+ resize" hint to the customizable-overview line)

No backend changes. No new env vars. No migrations.

---

## Task 1 — Registry: add `PanelWidth` + `defaultWidth` per panel + new `DEFAULT_OVERVIEW_LAYOUT` shape

**Files:**
- Modify: `frontend/src/lib/panelRegistry.ts`

This task changes a TYPE shape. Downstream files (the store, OverviewPage, AddPanelTile, SortablePanel) expect the OLD shape and will fail to typecheck after this task in isolation. We accept that — Task 2 fixes the store; Tasks 3–5 fix the consumers; the build only needs to pass after Task 5. **Skip the `npm run build` check inside Tasks 1–4; build only at the end of Task 5.**

- [ ] **Step 1: Replace the file with the new content**

Replace the ENTIRE content of `frontend/src/lib/panelRegistry.ts` with this:

```typescript
import type { ComponentType } from "react";

import AlertEventsPanel from "../components/AlertEventsPanel";
import DerivativesPanel from "../components/DerivativesPanel";
import ExchangeFlowsPanel from "../components/ExchangeFlowsPanel";
import MempoolPanel from "../components/MempoolPanel";
import NetworkActivityPanel from "../components/NetworkActivityPanel";
import OnchainVolumePanel from "../components/OnchainVolumePanel";
import OrderFlowPanel from "../components/OrderFlowPanel";
import PriceChart from "../components/PriceChart";
import PriceHero from "../components/PriceHero";
import SmartMoneyLeaderboard from "../components/SmartMoneyLeaderboard";
import StablecoinSupplyPanel from "../components/StablecoinSupplyPanel";
import VolumeStructurePanel from "../components/VolumeStructurePanel";
import WhaleTransfersPanel from "../components/WhaleTransfersPanel";

export type PageId = "overview" | "markets" | "onchain" | "mempool";

export type PanelWidth = 1 | 2 | 3 | 4;

export type PanelDef = {
  /** Stable kebab-case id; persisted to LocalStorage and used as drag id. */
  id: string;
  /** Display name in the customize popover and topbar nav. */
  label: string;
  /** The panel component. May accept zero props or panel-specific props. */
  component: ComponentType<any>;
  /** Page this panel belongs to when not on overview. */
  defaultPage: PageId;
  /** Default column span on the bento grid (1=S, 2=M, 3=L, 4=Full). */
  defaultWidth: PanelWidth;
  /** True for panels that only make sense on overview (PriceHero). */
  homeOnly?: boolean;
};

export const PANELS: PanelDef[] = [
  { id: "price-hero", label: "Price", component: PriceHero, defaultPage: "overview", defaultWidth: 4, homeOnly: true },
  { id: "price-chart", label: "Chart", component: PriceChart, defaultPage: "markets", defaultWidth: 3 },
  { id: "derivatives", label: "Derivatives", component: DerivativesPanel, defaultPage: "markets", defaultWidth: 2 },
  { id: "smart-money", label: "Smart money", component: SmartMoneyLeaderboard, defaultPage: "markets", defaultWidth: 2 },
  { id: "order-flow", label: "Order flow", component: OrderFlowPanel, defaultPage: "markets", defaultWidth: 2 },
  { id: "volume-structure", label: "Volume structure", component: VolumeStructurePanel, defaultPage: "markets", defaultWidth: 2 },
  { id: "exchange-flows", label: "Exchange flows", component: ExchangeFlowsPanel, defaultPage: "onchain", defaultWidth: 1 },
  { id: "stablecoin-supply", label: "Stablecoin supply", component: StablecoinSupplyPanel, defaultPage: "onchain", defaultWidth: 1 },
  { id: "onchain-volume", label: "On-chain volume", component: OnchainVolumePanel, defaultPage: "onchain", defaultWidth: 2 },
  { id: "network-activity", label: "Network activity", component: NetworkActivityPanel, defaultPage: "onchain", defaultWidth: 2 },
  { id: "whale-transfers", label: "Whale transfers", component: WhaleTransfersPanel, defaultPage: "onchain", defaultWidth: 2 },
  { id: "mempool", label: "Mempool", component: MempoolPanel, defaultPage: "mempool", defaultWidth: 2 },
  { id: "alerts", label: "Alerts", component: AlertEventsPanel, defaultPage: "mempool", defaultWidth: 2 },
];

export const PANELS_BY_ID: Record<string, PanelDef> = Object.fromEntries(
  PANELS.map((p) => [p.id, p]),
);

/** Default Overview layout. v2 shape: each entry carries an explicit width. */
export const DEFAULT_OVERVIEW_LAYOUT: { id: string; width: PanelWidth }[] = [
  { id: "price-hero", width: 4 },
  { id: "price-chart", width: 3 },
  { id: "exchange-flows", width: 1 },
  { id: "whale-transfers", width: 2 },
  { id: "smart-money", width: 2 },
];

/**
 * Static map of width → Tailwind class string used by `<SortablePanel>`.
 * Literal strings ensure Tailwind's PurgeCSS sees them at build time.
 *
 * The "responsive collapse" mapping intentionally lets a width-4 panel
 * span the whole row at every breakpoint (always full), and a width-1
 * panel widen at narrower viewports so it doesn't render absurdly small.
 */
export const SPAN_CLASS: Record<PanelWidth, string> = {
  1: "col-span-1",
  2: "col-span-1 md:col-span-2",
  3: "col-span-1 md:col-span-2 lg:col-span-3",
  4: "col-span-1 md:col-span-2 lg:col-span-3 xl:col-span-4",
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/panelRegistry.ts
git commit -m "feat(layout): registry v2 — defaultWidth per panel + SPAN_CLASS map"
```

(No build/typecheck this task — consumers are still on v1 shape. Build runs at end of Task 5.)

---

## Task 2 — Store: schema v2, `panels` shape, add `resize`, migrate v1 → v2

**Files:**
- Modify: `frontend/src/state/overviewLayout.ts`

- [ ] **Step 1: Replace the file**

Replace the ENTIRE content of `frontend/src/state/overviewLayout.ts` with this:

```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";

import {
  DEFAULT_OVERVIEW_LAYOUT,
  PANELS,
  PANELS_BY_ID,
  type PanelWidth,
} from "../lib/panelRegistry";

const STORAGE_KEY = "etherscope.overviewLayout";
const SCHEMA_VERSION = 2;

export type StoredPanel = { id: string; width: PanelWidth };

type State = {
  /** Schema version of the persisted shape; bumps invalidate stored layouts. */
  version: typeof SCHEMA_VERSION;
  panels: StoredPanel[];
  reorder: (activeId: string, overId: string) => void;
  add: (id: string, width?: PanelWidth) => void;
  remove: (id: string) => void;
  resize: (id: string, width: PanelWidth) => void;
  reset: () => void;
};

export const useOverviewLayout = create<State>()(
  persist(
    (set) => ({
      version: SCHEMA_VERSION,
      panels: DEFAULT_OVERVIEW_LAYOUT,
      reorder: (activeId, overId) =>
        set((s) => {
          const list = [...s.panels];
          const from = list.findIndex((p) => p.id === activeId);
          const to = list.findIndex((p) => p.id === overId);
          if (from === -1 || to === -1 || from === to) return s;
          const [moved] = list.splice(from, 1);
          list.splice(to, 0, moved);
          return { ...s, panels: list };
        }),
      add: (id, width) =>
        set((s) => {
          if (s.panels.some((p) => p.id === id)) return s;
          const def = PANELS_BY_ID[id];
          const w = width ?? def?.defaultWidth ?? 4;
          return { ...s, panels: [...s.panels, { id, width: w }] };
        }),
      remove: (id) =>
        set((s) => ({ ...s, panels: s.panels.filter((p) => p.id !== id) })),
      resize: (id, width) =>
        set((s) => ({
          ...s,
          panels: s.panels.map((p) => (p.id === id ? { ...p, width } : p)),
        })),
      reset: () => set((s) => ({ ...s, panels: DEFAULT_OVERVIEW_LAYOUT })),
    }),
    {
      name: STORAGE_KEY,
      version: SCHEMA_VERSION,
      migrate: (persisted: any, fromVersion) => {
        const known = new Set(PANELS.map((p) => p.id));

        if (fromVersion === 1 && persisted && Array.isArray(persisted.panelIds)) {
          // v1 → v2: panelIds: string[]  →  panels: { id, width }[]
          const panels: StoredPanel[] = persisted.panelIds
            .filter((id: string) => known.has(id))
            .map((id: string) => ({
              id,
              width: PANELS_BY_ID[id]?.defaultWidth ?? 4,
            }));
          return {
            version: SCHEMA_VERSION,
            panels: panels.length > 0 ? panels : DEFAULT_OVERVIEW_LAYOUT,
          };
        }

        if (
          fromVersion === SCHEMA_VERSION &&
          persisted &&
          Array.isArray(persisted.panels)
        ) {
          // Same version — prune unknown ids and clamp invalid widths.
          const cleaned: StoredPanel[] = persisted.panels
            .filter((p: any) => p && typeof p.id === "string" && known.has(p.id))
            .map((p: any) => ({
              id: p.id,
              width:
                p.width === 1 || p.width === 2 || p.width === 3 || p.width === 4
                  ? p.width
                  : (PANELS_BY_ID[p.id]?.defaultWidth ?? 4),
            }));
          return {
            version: SCHEMA_VERSION,
            panels: cleaned.length > 0 ? cleaned : DEFAULT_OVERVIEW_LAYOUT,
          };
        }

        // Unknown / corrupt — fall back.
        return { version: SCHEMA_VERSION, panels: DEFAULT_OVERVIEW_LAYOUT };
      },
    },
  ),
);
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/state/overviewLayout.ts
git commit -m "feat(layout): overview store v2 — {id,width} entries + resize() + v1 migrate"
```

---

## Task 3 — `<SortablePanel>`: width prop + `<SizeButtons>` in edit cluster

**Files:**
- Modify: `frontend/src/components/ui/SortablePanel.tsx`

- [ ] **Step 1: Replace the file**

Replace the ENTIRE content of `frontend/src/components/ui/SortablePanel.tsx` with this:

```tsx
import type { ReactNode } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { SPAN_CLASS, type PanelWidth } from "../../lib/panelRegistry";
import { useCustomizeMode } from "../../state/customizeMode";
import { useOverviewLayout } from "../../state/overviewLayout";
import ErrorBoundary from "./ErrorBoundary";

type Props = {
  id: string;
  label: string;
  width: PanelWidth;
  children: ReactNode;
};

function SizeButtons({ id, width }: { id: string; width: PanelWidth }) {
  const resize = useOverviewLayout((s) => s.resize);
  const sizes: { w: PanelWidth; label: string }[] = [
    { w: 1, label: "S" },
    { w: 2, label: "M" },
    { w: 3, label: "L" },
    { w: 4, label: "Full" },
  ];
  return (
    <div className="flex items-center text-[10px] divide-x divide-surface-border">
      {sizes.map(({ w, label }) => (
        <button
          key={w}
          type="button"
          onClick={() => resize(id, w)}
          className={
            "px-1.5 py-0.5 transition " +
            (width === w
              ? "bg-brand/30 text-brand-soft"
              : "text-slate-400 hover:text-slate-200 hover:bg-surface-raised")
          }
          title={`Resize to ${label}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export default function SortablePanel({ id, label, width, children }: Props) {
  const editing = useCustomizeMode((s) => s.editing);
  const remove = useOverviewLayout((s) => s.remove);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <section
      ref={setNodeRef}
      id={id}
      style={style}
      className={`scroll-mt-20 relative ${SPAN_CLASS[width]}`}
    >
      {editing && (
        <div className="absolute -top-2 right-2 z-10 flex items-center gap-1 bg-surface-card/95 backdrop-blur rounded-md ring-1 ring-surface-border px-1 py-0.5 shadow-card">
          <SizeButtons id={id} width={width} />
          <button
            type="button"
            {...attributes}
            {...listeners}
            className="px-1.5 py-0.5 text-slate-400 hover:text-slate-200 cursor-grab active:cursor-grabbing"
            aria-label={`Drag ${label}`}
            title={`Drag ${label}`}
          >
            ⋮⋮
          </button>
          <button
            type="button"
            onClick={() => remove(id)}
            className="px-1.5 py-0.5 text-slate-400 hover:text-down"
            aria-label={`Remove ${label}`}
            title={`Remove ${label}`}
          >
            ×
          </button>
        </div>
      )}
      <ErrorBoundary label={label}>{children}</ErrorBoundary>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ui/SortablePanel.tsx
git commit -m "feat(layout): SortablePanel applies col-span + renders S/M/L/Full buttons"
```

---

## Task 4 — `<AddPanelTile>`: read `panels` not `panelIds`

**Files:**
- Modify: `frontend/src/components/ui/AddPanelTile.tsx`

- [ ] **Step 1: Replace the file**

Replace the ENTIRE content of `frontend/src/components/ui/AddPanelTile.tsx` with this:

```tsx
import { useEffect, useRef, useState } from "react";

import { PANELS } from "../../lib/panelRegistry";
import { useOverviewLayout } from "../../state/overviewLayout";

export default function AddPanelTile() {
  const panels = useOverviewLayout((s) => s.panels);
  const add = useOverviewLayout((s) => s.add);
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  // Click outside closes the popover.
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const presentIds = new Set(panels.map((p) => p.id));
  const available = PANELS.filter((p) => !presentIds.has(p.id));

  return (
    <div ref={wrapperRef} className="relative col-span-1 md:col-span-2 lg:col-span-3 xl:col-span-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full rounded-xl border border-dashed border-surface-border text-slate-500 hover:text-slate-200 hover:border-surface-divider py-8 text-sm transition"
      >
        + Add panel
      </button>
      {open && (
        <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 w-64 rounded-lg border border-surface-border bg-surface-card shadow-card p-2 z-30">
          <div className="text-[10px] font-semibold tracking-widest text-slate-500 uppercase px-2 py-1.5">
            Add to overview
          </div>
          {available.length === 0 ? (
            <div className="px-3 py-2 text-xs text-slate-500">All panels are on overview.</div>
          ) : (
            <ul>
              {available.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => {
                      add(p.id);
                      setOpen(false);
                    }}
                    className="w-full text-left text-sm px-3 py-1.5 rounded hover:bg-surface-raised text-slate-200"
                  >
                    {p.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
```

(Note: the wrapping `<div>` now carries the same full-width responsive col-span class so the "+ Add panel" tile always fills the last row of the bento grid.)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ui/AddPanelTile.tsx
git commit -m "feat(layout): AddPanelTile reads v2 panels shape + spans full grid row"
```

---

## Task 5 — `OverviewPage`: 4-col grid + iterate `panels` with width

**Files:**
- Modify: `frontend/src/routes/OverviewPage.tsx`

This is the task that makes the build green again. After this commit, every consumer is on the v2 shape.

- [ ] **Step 1: Replace the file**

Replace the ENTIRE content of `frontend/src/routes/OverviewPage.tsx` with this:

```tsx
import { useEffect, useState } from "react";
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  rectSortingStrategy,
} from "@dnd-kit/sortable";

import type { Timeframe } from "../api";
import { PANELS_BY_ID } from "../lib/panelRegistry";
import { useCustomizeMode } from "../state/customizeMode";
import { useOverviewLayout } from "../state/overviewLayout";
import AddPanelTile from "../components/ui/AddPanelTile";
import SortablePanel from "../components/ui/SortablePanel";

export default function OverviewPage() {
  const panels = useOverviewLayout((s) => s.panels);
  const reorder = useOverviewLayout((s) => s.reorder);
  const editing = useCustomizeMode((s) => s.editing);
  const exit = useCustomizeMode((s) => s.exit);
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  // Escape exits customize mode.
  useEffect(() => {
    if (!editing) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") exit();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, exit]);

  function handleDragEnd(e: DragEndEvent) {
    if (e.over && e.active.id !== e.over.id) {
      reorder(e.active.id as string, e.over.id as string);
    }
  }

  // Empty placeholder, but only when NOT editing — in edit mode the
  // AddPanelTile must remain visible so the user can add the first panel.
  if (panels.length === 0 && !editing) {
    return (
      <div className="text-center text-sm text-slate-500 py-20">
        Click <span className="text-slate-300">Customize</span> to add panels to your overview.
      </div>
    );
  }

  const items = panels.map((p) => p.id);

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <SortableContext items={items} strategy={rectSortingStrategy}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {panels.map((p) => {
            const def = PANELS_BY_ID[p.id];
            if (!def) return null;
            const Component = def.component;
            const props =
              p.id === "price-chart"
                ? { timeframe, onTimeframeChange: setTimeframe }
                : {};
            return (
              <SortablePanel key={p.id} id={p.id} label={def.label} width={p.width}>
                <Component {...props} />
              </SortablePanel>
            );
          })}
          {editing && <AddPanelTile />}
        </div>
      </SortableContext>
    </DndContext>
  );
}
```

(The sorting strategy switches from `verticalListSortingStrategy` to `rectSortingStrategy` because panels can now sit beside each other in a row — vertical-only sorting would mis-locate the drop target on a multi-column grid.)

- [ ] **Step 2: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds (`✓ built in N.NNs`). All consumers are now on the v2 shape and types reconcile.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/OverviewPage.tsx
git commit -m "feat(layout): bento 4-col grid container + width-aware panel render"
```

---

## Task 6 — CLAUDE.md note + manual smoke

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Restart the local stack to pick up the new frontend bundle**

From the repo root:

```bash
make down && make up
```

Wait ~10 s.

- [ ] **Step 2: Smoke test in the browser**

Open `http://localhost:5173`, log in, hard-refresh (`Cmd+Shift+R`). Verify each — STOP on any failure:

- [ ] **First-time migration (clean state).** In DevTools → Application → LocalStorage, delete `etherscope.overviewLayout`. Reload. Overview shows 5 default panels at their default widths: PriceHero=Full row, PriceChart=L (¾) + ExchangeFlows=S (¼) on the second row, then Whales=M and SmartMoney=M side-by-side.
- [ ] **v1 migration.** Set the LocalStorage value manually to `{"state":{"version":1,"panelIds":["price-chart","whale-transfers"]},"version":1}` and reload. The two panels render at their `defaultWidth` (Chart at L, Whales at M).
- [ ] **Resize buttons.** Click "Customize" → each panel sprouts S/M/L/Full + drag handle + ×. Click "S" on PriceChart — it shrinks to ¼ width; the next panel reflows beside it. Click "Full" on Chart — it occupies the whole row.
- [ ] **Persistence.** Reload — your widths persist.
- [ ] **Reorder preserves width.** Drag a wide panel below a narrow one; both keep their widths.
- [ ] **Add a panel.** Click "+ Add panel" → click any panel → it appears at the end at its `defaultWidth`.
- [ ] **Remove a panel.** Click × → gone; refresh → still gone.
- [ ] **Esc still exits.** Customize → Escape → buttons disappear.
- [ ] **Mobile (375 px viewport, DevTools).** Customize button hidden. Every panel renders full-width single-column regardless of stored width. No drag handles.
- [ ] **lg viewport (1024 px).** Width-4 panels still span the whole row. Width-3 panels span the whole row at lg (3 of 3 cols). Width-2 panels are half-width. Width-1 panels are third-width.
- [ ] **xl viewport (≥1280 px).** Up to 4 columns; full bento layout.
- [ ] **Existing features still work.** Address click → wallet drawer. Live ticker still ticks.
- [ ] **LocalStorage corruption.** Set the storage value to `{}` and reload → falls back to defaults; no crash.

- [ ] **Step 3: Update CLAUDE.md**

Edit `CLAUDE.md`. Find the existing customizable-overview line (under "## UI polish"):

```markdown
- Customizable overview ✅ React Router 4-page split (`Overview · Markets · Onchain · Mempool`); overview supports drag-to-reorder + add/remove via `dnd-kit/sortable`, persisted to LocalStorage with a versioned schema; category pages are fixed-in-code, derived from a single `lib/panelRegistry.ts`. Desktop only (`≥md`); mobile renders a clean default stack. Spec: `docs/superpowers/specs/2026-05-01-customizable-layout-design.md`.
```

Replace with:

```markdown
- Customizable overview ✅ React Router 4-page split (`Overview · Markets · Onchain · Mempool`); overview supports drag-to-reorder, add/remove, and bento-grid resize (S/M/L/Full → 1/2/3/4 cols) via `dnd-kit/sortable` + a 4-col CSS grid, persisted to LocalStorage (schema v2); category pages are fixed-in-code, derived from a single `lib/panelRegistry.ts`. Desktop only (`≥md`); mobile renders a clean default stack. Specs: `docs/superpowers/specs/2026-05-01-customizable-layout-design.md`, `docs/superpowers/specs/2026-05-01-bento-grid-resize-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(layout): note bento-grid resize shipping under UI polish"
```

---

## Self-review

**Spec coverage:**

- §UX: edit-mode size buttons → Task 3 (`<SizeButtons>` inside SortablePanel's cluster).
- §UX: read-mode width → Task 3 (applies `SPAN_CLASS[width]` outside edit mode).
- §UX: mobile collapses → Task 1 (the `SPAN_CLASS` strings) + Task 5 (`grid-cols-1 md:grid-cols-2 ...`).
- §Grid behaviour: 4-col container with responsive collapse → Task 5.
- §Grid behaviour: SPAN_CLASS literal map (Tailwind purge friendly) → Task 1.
- §Architecture: stored shape v2 (`{id, width}` entries) → Task 2.
- §Architecture: registry adds `defaultWidth` + `PanelWidth` type → Task 1.
- §Migration v1 → v2 (map each id to its `defaultWidth`) → Task 2 (`migrate` function).
- §Store API: add `resize(id, width)`, `add(id, width?)` defaulting from registry → Task 2.
- §`<SortablePanel>` accepts `width`, applies span, renders SizeButtons in edit mode → Task 3.
- §`<AddPanelTile>` reads new shape → Task 4.
- §`<OverviewPage>` iterates `panels` not `panelIds`, passes `width` → Task 5.
- §Sorting strategy needs to be rect (not vertical) for grid → Task 5.
- §Edge cases: clamp invalid stored widths → Task 2 migrate (the v2 → v2 path includes the clamp).
- §Tests: `npm run build` runs at end of Task 5; manual smoke checklist runs in Task 6.
- §CLAUDE.md note → Task 6.
- §Risks: bento gaps, PurgeCSS safety, first-paint sync — all addressed by design choices in Tasks 1, 5.

**Placeholder scan:** none — every step has runnable code or commands.

**Type consistency:**
- `PanelWidth = 1 | 2 | 3 | 4` defined in Task 1; consumed in Tasks 2 (`StoredPanel`), 3 (`Props.width`), 5 (passes `p.width`).
- `StoredPanel = { id: string; width: PanelWidth }` defined in Task 2; matches `DEFAULT_OVERVIEW_LAYOUT` shape from Task 1.
- Store API `panels: StoredPanel[]`, `resize(id, width)`, `add(id, width?)`, `remove(id)`, `reorder(activeId, overId)`, `reset()` — all types reconcile across Tasks 2 (declared), 3 (`resize`, `remove` consumed), 4 (`add`, `panels` consumed), 5 (`panels`, `reorder` consumed).
- `SPAN_CLASS: Record<PanelWidth, string>` exported from Task 1, consumed in Task 3.
- `SortablePanel` props `{ id, label, width, children }` — Task 3 declares; Task 5 passes the matching shape.
- The single intentional type-break window is between Task 1 and Task 5 (registry shape changes before consumers update). Each task commits independently and the build is exercised at the end of Task 5; this is documented in Task 1's preamble. No subagent should panic at intermediate `npm run build` failures because we don't run it inside Tasks 1–4.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-01-bento-grid-resize.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
