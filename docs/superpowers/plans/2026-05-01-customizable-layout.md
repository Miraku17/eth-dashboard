# Customizable Overview + 4-page Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace today's flat-stack `App.tsx` with a 4-page React Router app (`Overview · Markets · Onchain · Mempool`) where Overview supports drag-to-reorder + add/remove of panels, persisted to LocalStorage. Category pages render fixed registry-driven panel lists.

**Architecture:** Add `react-router-dom` and `@dnd-kit/sortable`. Introduce a single `panelRegistry.ts` listing all 13 panels with their default page. Two Zustand stores: `overviewLayout` (persisted) for the user's overview ordering, `customizeMode` (in-memory) for the edit toggle. `App.tsx` becomes a `<BrowserRouter>` shell wrapping four route components. `Topbar` becomes a `NavLink`-based 4-link nav + a Customize/Done button visible only on `/` at `≥md`.

**Tech Stack:** React 18 + TypeScript + Vite + Tailwind + Zustand (already installed), plus new: `react-router-dom`, `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`. No backend changes.

**Spec:** `docs/superpowers/specs/2026-05-01-customizable-layout-design.md`.

**File map:**
- Create:
  - `frontend/src/lib/panelRegistry.ts`
  - `frontend/src/state/overviewLayout.ts`
  - `frontend/src/state/customizeMode.ts`
  - `frontend/src/components/DashboardShell.tsx`
  - `frontend/src/routes/OverviewPage.tsx`
  - `frontend/src/routes/MarketsPage.tsx`
  - `frontend/src/routes/OnchainPage.tsx`
  - `frontend/src/routes/MempoolPage.tsx`
  - `frontend/src/components/ui/SortablePanel.tsx`
  - `frontend/src/components/ui/AddPanelTile.tsx`
- Modify:
  - `frontend/src/App.tsx` (routes-only shell)
  - `frontend/src/components/Topbar.tsx` (router NavLinks + Customize button)
  - `frontend/package.json` + `package-lock.json` (new deps)
  - `CLAUDE.md` (one-line note under "## UI polish")

No frontend test infra exists; validation is `npm run build` plus the manual smoke checklist in Task 9.

---

## Task 1 — Install deps + create the panel registry

**Files:**
- Modify: `frontend/package.json` + `package-lock.json` (via npm)
- Create: `frontend/src/lib/panelRegistry.ts`

- [ ] **Step 1: Install dependencies**

```bash
cd frontend && npm i react-router-dom @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities
```

Verify the new entries appear under `"dependencies"` in `frontend/package.json`.

- [ ] **Step 2: Create the panel registry**

Create `frontend/src/lib/panelRegistry.ts` with this exact content:

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

export type PanelDef = {
  /** Stable kebab-case id; persisted to LocalStorage and used as drag id. */
  id: string;
  /** Display name in the customize popover and topbar nav. */
  label: string;
  /** The panel component. May accept zero props or panel-specific props. */
  component: ComponentType<any>;
  /** Page this panel belongs to when not on overview. */
  defaultPage: PageId;
  /** True for panels that only make sense on overview (PriceHero). */
  homeOnly?: boolean;
};

export const PANELS: PanelDef[] = [
  { id: "price-hero", label: "Price", component: PriceHero, defaultPage: "overview", homeOnly: true },
  { id: "price-chart", label: "Chart", component: PriceChart, defaultPage: "markets" },
  { id: "derivatives", label: "Derivatives", component: DerivativesPanel, defaultPage: "markets" },
  { id: "smart-money", label: "Smart money", component: SmartMoneyLeaderboard, defaultPage: "markets" },
  { id: "order-flow", label: "Order flow", component: OrderFlowPanel, defaultPage: "markets" },
  { id: "volume-structure", label: "Volume structure", component: VolumeStructurePanel, defaultPage: "markets" },
  { id: "exchange-flows", label: "Exchange flows", component: ExchangeFlowsPanel, defaultPage: "onchain" },
  { id: "stablecoin-supply", label: "Stablecoin supply", component: StablecoinSupplyPanel, defaultPage: "onchain" },
  { id: "onchain-volume", label: "On-chain volume", component: OnchainVolumePanel, defaultPage: "onchain" },
  { id: "network-activity", label: "Network activity", component: NetworkActivityPanel, defaultPage: "onchain" },
  { id: "whale-transfers", label: "Whale transfers", component: WhaleTransfersPanel, defaultPage: "onchain" },
  { id: "mempool", label: "Mempool", component: MempoolPanel, defaultPage: "mempool" },
  { id: "alerts", label: "Alerts", component: AlertEventsPanel, defaultPage: "mempool" },
];

export const PANELS_BY_ID: Record<string, PanelDef> = Object.fromEntries(
  PANELS.map((p) => [p.id, p]),
);

/** Default panels on the overview when no customization has happened yet. */
export const DEFAULT_OVERVIEW_LAYOUT: string[] = [
  "price-hero",
  "price-chart",
  "whale-transfers",
  "exchange-flows",
  "smart-money",
];
```

- [ ] **Step 3: Build to verify imports**

```bash
cd frontend && npm run build
```

Expected: succeeds. The registry file is unused so far, but every panel import must resolve.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/panelRegistry.ts
git commit -m "feat(layout): add router/dnd-kit deps + panel registry"
```

---

## Task 2 — Zustand stores for layout + customize mode

**Files:**
- Create: `frontend/src/state/overviewLayout.ts`
- Create: `frontend/src/state/customizeMode.ts`

- [ ] **Step 1: Create `overviewLayout.ts`**

Create `frontend/src/state/overviewLayout.ts`:

```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";

import { DEFAULT_OVERVIEW_LAYOUT, PANELS } from "../lib/panelRegistry";

const STORAGE_KEY = "etherscope.overviewLayout";
const SCHEMA_VERSION = 1;

type State = {
  /** Schema version of the persisted shape; bumps invalidate stored layouts. */
  version: typeof SCHEMA_VERSION;
  panelIds: string[];
  reorder: (activeId: string, overId: string) => void;
  add: (id: string) => void;
  remove: (id: string) => void;
  reset: () => void;
};

export const useOverviewLayout = create<State>()(
  persist(
    (set) => ({
      version: SCHEMA_VERSION,
      panelIds: DEFAULT_OVERVIEW_LAYOUT,
      reorder: (activeId, overId) =>
        set((s) => {
          const ids = [...s.panelIds];
          const from = ids.indexOf(activeId);
          const to = ids.indexOf(overId);
          if (from === -1 || to === -1 || from === to) return s;
          ids.splice(from, 1);
          ids.splice(to, 0, activeId);
          return { ...s, panelIds: ids };
        }),
      add: (id) =>
        set((s) =>
          s.panelIds.includes(id) ? s : { ...s, panelIds: [...s.panelIds, id] },
        ),
      remove: (id) =>
        set((s) => ({ ...s, panelIds: s.panelIds.filter((x) => x !== id) })),
      reset: () => set((s) => ({ ...s, panelIds: DEFAULT_OVERVIEW_LAYOUT })),
    }),
    {
      name: STORAGE_KEY,
      version: SCHEMA_VERSION,
      // On load, drop any panel IDs no longer in the registry; on unknown
      // version fall back to default. Both prevent stale state from
      // surviving a panel removal or schema bump.
      migrate: (persisted: any, fromVersion) => {
        if (fromVersion !== SCHEMA_VERSION || !persisted) {
          return {
            version: SCHEMA_VERSION,
            panelIds: DEFAULT_OVERVIEW_LAYOUT,
          };
        }
        const known = new Set(PANELS.map((p) => p.id));
        const cleaned = (persisted.panelIds ?? []).filter((id: string) =>
          known.has(id),
        );
        return {
          ...persisted,
          panelIds: cleaned.length > 0 ? cleaned : DEFAULT_OVERVIEW_LAYOUT,
        };
      },
    },
  ),
);
```

- [ ] **Step 2: Create `customizeMode.ts`**

Create `frontend/src/state/customizeMode.ts`:

```typescript
import { create } from "zustand";

type State = {
  editing: boolean;
  toggle: () => void;
  exit: () => void;
};

export const useCustomizeMode = create<State>((set) => ({
  editing: false,
  toggle: () => set((s) => ({ editing: !s.editing })),
  exit: () => set({ editing: false }),
}));
```

- [ ] **Step 3: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/state/overviewLayout.ts frontend/src/state/customizeMode.ts
git commit -m "feat(layout): zustand stores for overview layout + customize mode"
```

---

## Task 3 — Extract `<DashboardShell>` + wire up `<BrowserRouter>`

This is a behaviour-neutral refactor: same panels still render, but inside a single Overview route. Drag/customize/category pages come in subsequent tasks. **The visible UI must be identical to today after this task.**

**Files:**
- Create: `frontend/src/components/DashboardShell.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `DashboardShell.tsx`**

Create `frontend/src/components/DashboardShell.tsx`:

```tsx
import { Outlet } from "react-router-dom";

import Topbar from "./Topbar";
import { useGlobalShortcuts } from "../hooks/useGlobalShortcuts";

export default function DashboardShell() {
  useGlobalShortcuts();
  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="mx-auto max-w-[1600px] px-4 sm:px-6 py-6 space-y-6">
        <Outlet />
        <footer className="pt-4 pb-6 text-center text-[11px] text-slate-600">
          Data: Binance · Dune Analytics · Alchemy · Etherscan · CoinGecko
        </footer>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Move the existing rendered tree into a temporary `OverviewPage`**

Create `frontend/src/routes/OverviewPage.tsx` with EXACTLY the panel content currently inside `App.tsx`'s `<main>`. This is a verbatim move — no behaviour change yet. Drag, customization, and registry-driven rendering land in Task 6.

Create `frontend/src/routes/OverviewPage.tsx`:

```tsx
import { useState, type ReactNode } from "react";

import type { Timeframe } from "../api";
import AlertEventsPanel from "../components/AlertEventsPanel";
import DerivativesPanel from "../components/DerivativesPanel";
import ExchangeFlowsPanel from "../components/ExchangeFlowsPanel";
import MempoolPanel from "../components/MempoolPanel";
import NetworkActivityPanel from "../components/NetworkActivityPanel";
import OnchainVolumePanel from "../components/OnchainVolumePanel";
import OrderFlowPanel from "../components/OrderFlowPanel";
import PriceChart from "../components/PriceChart";
import SmartMoneyLeaderboard from "../components/SmartMoneyLeaderboard";
import PriceHero from "../components/PriceHero";
import StablecoinSupplyPanel from "../components/StablecoinSupplyPanel";
import VolumeStructurePanel from "../components/VolumeStructurePanel";
import WhaleTransfersPanel from "../components/WhaleTransfersPanel";
import ErrorBoundary from "../components/ui/ErrorBoundary";

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

export default function OverviewPage() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  return (
    <>
      <Guarded label="Price" id="overview">
        <PriceHero />
      </Guarded>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2">
          <Guarded label="Chart">
            <PriceChart timeframe={timeframe} onTimeframeChange={setTimeframe} />
          </Guarded>
        </div>
        <div className="space-y-6">
          <Guarded label="Exchange flows" id="flows">
            <ExchangeFlowsPanel />
          </Guarded>
          <Guarded label="Stablecoin supply">
            <StablecoinSupplyPanel />
          </Guarded>
        </div>
      </div>

      <Guarded label="Derivatives" id="derivatives">
        <DerivativesPanel />
      </Guarded>
      <Guarded label="Smart money" id="smart-money">
        <SmartMoneyLeaderboard />
      </Guarded>
      <Guarded label="Order flow" id="order-flow">
        <OrderFlowPanel />
      </Guarded>
      <Guarded label="Volume structure" id="volume-structure">
        <VolumeStructurePanel />
      </Guarded>
      <Guarded label="Network activity">
        <NetworkActivityPanel />
      </Guarded>
      <Guarded label="On-chain volume">
        <OnchainVolumePanel />
      </Guarded>
      <Guarded label="Whale transfers" id="whales">
        <WhaleTransfersPanel />
      </Guarded>
      <Guarded label="Mempool" id="mempool">
        <MempoolPanel />
      </Guarded>
      <Guarded label="Alerts" id="alerts">
        <AlertEventsPanel />
      </Guarded>
    </>
  );
}
```

- [ ] **Step 3: Replace `App.tsx`**

Replace the entire content of `frontend/src/App.tsx` with:

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";

import AuthGate from "./components/AuthGate";
import DashboardShell from "./components/DashboardShell";
import WalletDrawer from "./components/WalletDrawer";
import OverviewPage from "./routes/OverviewPage";

export default function App() {
  return (
    <AuthGate>
      <BrowserRouter>
        <Routes>
          <Route element={<DashboardShell />}>
            <Route index element={<OverviewPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <WalletDrawer />
    </AuthGate>
  );
}
```

- [ ] **Step 4: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds. Bundle should be ~10–20 KB larger (router payload).

- [ ] **Step 5: Smoke check (controller-side, optional)**

Bring up the local dev frontend (`npm run dev` if not already up via docker) and visually confirm the page looks identical to before. **No new pages yet** — this task is just the routing skeleton.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/DashboardShell.tsx \
        frontend/src/routes/OverviewPage.tsx \
        frontend/src/App.tsx
git commit -m "refactor(layout): wrap dashboard in DashboardShell + BrowserRouter"
```

---

## Task 4 — Add the three category pages

**Files:**
- Create: `frontend/src/routes/MarketsPage.tsx`
- Create: `frontend/src/routes/OnchainPage.tsx`
- Create: `frontend/src/routes/MempoolPage.tsx`
- Modify: `frontend/src/App.tsx` (register the new routes)

- [ ] **Step 1: Create `MarketsPage.tsx`**

Create `frontend/src/routes/MarketsPage.tsx`:

```tsx
import { useState, type ReactNode } from "react";

import type { Timeframe } from "../api";
import { PANELS } from "../lib/panelRegistry";
import ErrorBoundary from "../components/ui/ErrorBoundary";

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

const PANELS_FOR_PAGE = PANELS.filter((p) => p.defaultPage === "markets");

export default function MarketsPage() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  return (
    <>
      {PANELS_FOR_PAGE.map((p) => {
        const Component = p.component;
        const props =
          p.id === "price-chart"
            ? { timeframe, onTimeframeChange: setTimeframe }
            : {};
        return (
          <Guarded key={p.id} label={p.label} id={p.id}>
            <Component {...props} />
          </Guarded>
        );
      })}
    </>
  );
}
```

- [ ] **Step 2: Create `OnchainPage.tsx`**

Create `frontend/src/routes/OnchainPage.tsx`:

```tsx
import type { ReactNode } from "react";

import { PANELS } from "../lib/panelRegistry";
import ErrorBoundary from "../components/ui/ErrorBoundary";

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

const PANELS_FOR_PAGE = PANELS.filter((p) => p.defaultPage === "onchain");

export default function OnchainPage() {
  return (
    <>
      {PANELS_FOR_PAGE.map((p) => {
        const Component = p.component;
        return (
          <Guarded key={p.id} label={p.label} id={p.id}>
            <Component />
          </Guarded>
        );
      })}
    </>
  );
}
```

- [ ] **Step 3: Create `MempoolPage.tsx`**

Create `frontend/src/routes/MempoolPage.tsx`:

```tsx
import type { ReactNode } from "react";

import { PANELS } from "../lib/panelRegistry";
import ErrorBoundary from "../components/ui/ErrorBoundary";

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

const PANELS_FOR_PAGE = PANELS.filter((p) => p.defaultPage === "mempool");

export default function MempoolPage() {
  return (
    <>
      {PANELS_FOR_PAGE.map((p) => {
        const Component = p.component;
        return (
          <Guarded key={p.id} label={p.label} id={p.id}>
            <Component />
          </Guarded>
        );
      })}
    </>
  );
}
```

- [ ] **Step 4: Register the new routes in `App.tsx`**

Edit `frontend/src/App.tsx`. Replace the entire file with:

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";

import AuthGate from "./components/AuthGate";
import DashboardShell from "./components/DashboardShell";
import WalletDrawer from "./components/WalletDrawer";
import MarketsPage from "./routes/MarketsPage";
import MempoolPage from "./routes/MempoolPage";
import OnchainPage from "./routes/OnchainPage";
import OverviewPage from "./routes/OverviewPage";

export default function App() {
  return (
    <AuthGate>
      <BrowserRouter>
        <Routes>
          <Route element={<DashboardShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="markets" element={<MarketsPage />} />
            <Route path="onchain" element={<OnchainPage />} />
            <Route path="mempool" element={<MempoolPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <WalletDrawer />
    </AuthGate>
  );
}
```

- [ ] **Step 5: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/MarketsPage.tsx \
        frontend/src/routes/OnchainPage.tsx \
        frontend/src/routes/MempoolPage.tsx \
        frontend/src/App.tsx
git commit -m "feat(layout): add Markets / Onchain / Mempool routes"
```

---

## Task 5 — Topbar: 4-link router nav + Customize button

**Files:**
- Modify: `frontend/src/components/Topbar.tsx`

- [ ] **Step 1: Replace the NAV array + nav block + add Customize button**

Open `frontend/src/components/Topbar.tsx`. Apply these changes:

**a)** Update imports near the top — add `NavLink` and `useLocation` from react-router-dom, and the customize-mode store:

```tsx
import { NavLink, useLocation } from "react-router-dom";
import { useCustomizeMode } from "../state/customizeMode";
```

**b)** Replace the existing `NAV` array (lines 7–13) with:

```tsx
const NAV: readonly { label: string; to: string }[] = [
  { label: "Overview", to: "/" },
  { label: "Markets", to: "/markets" },
  { label: "Onchain", to: "/onchain" },
  { label: "Mempool", to: "/mempool" },
];
```

**c)** Replace the existing `<nav>` block (the one rendering `NAV.map` with anchor `<a href={"#"+id}>` tags) with:

```tsx
          <nav className="flex items-center gap-1">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) =>
                  "px-3 py-1.5 text-sm rounded-md transition " +
                  (isActive
                    ? "text-slate-100 bg-surface-raised/80"
                    : "text-slate-400 hover:text-slate-200 hover:bg-surface-raised/60")
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
```

(Removed the `hidden md:flex` modifier — nav now shows on all viewports per the spec.)

**d)** Add a `CustomizeButton` component above the existing `UserMenu` function:

```tsx
function CustomizeButton() {
  const location = useLocation();
  const editing = useCustomizeMode((s) => s.editing);
  const toggle = useCustomizeMode((s) => s.toggle);
  const isOverview = location.pathname === "/";
  if (!isOverview) return null;
  return (
    <button
      onClick={toggle}
      className="hidden md:inline-flex items-center gap-2 text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded-md border border-transparent hover:border-surface-border"
    >
      {editing ? "Done" : "Customize"}
    </button>
  );
}
```

**e)** Mount `<CustomizeButton />` inside the right-side cluster, immediately before the `<UserMenu />` (within the existing `<div className="relative flex items-center gap-4">` block):

```tsx
          <CustomizeButton />
          <UserMenu />
```

- [ ] **Step 2: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Topbar.tsx
git commit -m "feat(layout): router NavLinks + Customize button in Topbar"
```

---

## Task 6 — Overview becomes registry-driven (still no drag yet)

This task replaces the verbatim `OverviewPage` body (from Task 3) with a registry-driven mapped list. Drag-reorder lands in Task 7. By the end of this task, the overview should look like a clean stack of `DEFAULT_OVERVIEW_LAYOUT` panels: PriceHero, PriceChart, WhaleTransfers, ExchangeFlows, SmartMoney.

**Files:**
- Modify: `frontend/src/routes/OverviewPage.tsx`

- [ ] **Step 1: Replace OverviewPage with the registry-driven version**

Replace the entire content of `frontend/src/routes/OverviewPage.tsx` with:

```tsx
import { useState, type ReactNode } from "react";

import type { Timeframe } from "../api";
import { PANELS_BY_ID } from "../lib/panelRegistry";
import { useOverviewLayout } from "../state/overviewLayout";
import ErrorBoundary from "../components/ui/ErrorBoundary";

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

export default function OverviewPage() {
  const panelIds = useOverviewLayout((s) => s.panelIds);
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  if (panelIds.length === 0) {
    return (
      <div className="text-center text-sm text-slate-500 py-20">
        Click <span className="text-slate-300">Customize</span> to add panels to your overview.
      </div>
    );
  }

  return (
    <>
      {panelIds.map((id) => {
        const def = PANELS_BY_ID[id];
        if (!def) return null;
        const Component = def.component;
        const props =
          id === "price-chart"
            ? { timeframe, onTimeframeChange: setTimeframe }
            : {};
        return (
          <Guarded key={id} label={def.label} id={id}>
            <Component {...props} />
          </Guarded>
        );
      })}
    </>
  );
}
```

- [ ] **Step 2: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/OverviewPage.tsx
git commit -m "feat(layout): overview renders from panelRegistry + zustand layout"
```

---

## Task 7 — Drag-reorder via `dnd-kit/sortable`

This task wires drag-to-reorder. Drag handles are only visible when `customizeMode.editing === true`.

**Files:**
- Create: `frontend/src/components/ui/SortablePanel.tsx`
- Modify: `frontend/src/routes/OverviewPage.tsx`

- [ ] **Step 1: Create `SortablePanel.tsx`**

Create `frontend/src/components/ui/SortablePanel.tsx`:

```tsx
import type { ReactNode } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { useCustomizeMode } from "../../state/customizeMode";
import { useOverviewLayout } from "../../state/overviewLayout";
import ErrorBoundary from "./ErrorBoundary";

type Props = {
  id: string;
  label: string;
  children: ReactNode;
};

export default function SortablePanel({ id, label, children }: Props) {
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
      className="scroll-mt-20 relative"
    >
      {editing && (
        <div className="absolute -top-2 right-2 z-10 flex items-center gap-1 bg-surface-card/95 backdrop-blur rounded-md ring-1 ring-surface-border px-1 py-0.5 shadow-card">
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

- [ ] **Step 2: Wire `<DndContext>` + `<SortableContext>` into OverviewPage**

Replace the entire content of `frontend/src/routes/OverviewPage.tsx` with:

```tsx
import { useState } from "react";
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
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";

import type { Timeframe } from "../api";
import { PANELS_BY_ID } from "../lib/panelRegistry";
import { useOverviewLayout } from "../state/overviewLayout";
import SortablePanel from "../components/ui/SortablePanel";

export default function OverviewPage() {
  const panelIds = useOverviewLayout((s) => s.panelIds);
  const reorder = useOverviewLayout((s) => s.reorder);
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function handleDragEnd(e: DragEndEvent) {
    if (e.over && e.active.id !== e.over.id) {
      reorder(e.active.id as string, e.over.id as string);
    }
  }

  if (panelIds.length === 0) {
    return (
      <div className="text-center text-sm text-slate-500 py-20">
        Click <span className="text-slate-300">Customize</span> to add panels to your overview.
      </div>
    );
  }

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <SortableContext items={panelIds} strategy={verticalListSortingStrategy}>
        <div className="space-y-6">
          {panelIds.map((id) => {
            const def = PANELS_BY_ID[id];
            if (!def) return null;
            const Component = def.component;
            const props =
              id === "price-chart"
                ? { timeframe, onTimeframeChange: setTimeframe }
                : {};
            return (
              <SortablePanel key={id} id={id} label={def.label}>
                <Component {...props} />
              </SortablePanel>
            );
          })}
        </div>
      </SortableContext>
    </DndContext>
  );
}
```

- [ ] **Step 3: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ui/SortablePanel.tsx \
        frontend/src/routes/OverviewPage.tsx
git commit -m "feat(layout): drag-to-reorder via dnd-kit/sortable on overview"
```

---

## Task 8 — Add-panel tile + popover

**Files:**
- Create: `frontend/src/components/ui/AddPanelTile.tsx`
- Modify: `frontend/src/routes/OverviewPage.tsx` (mount the tile when editing)

- [ ] **Step 1: Create `AddPanelTile.tsx`**

Create `frontend/src/components/ui/AddPanelTile.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";

import { PANELS } from "../../lib/panelRegistry";
import { useOverviewLayout } from "../../state/overviewLayout";

export default function AddPanelTile() {
  const panelIds = useOverviewLayout((s) => s.panelIds);
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

  const available = PANELS.filter((p) => !panelIds.includes(p.id));

  return (
    <div ref={wrapperRef} className="relative">
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

- [ ] **Step 2: Mount `<AddPanelTile />` when editing**

Edit `frontend/src/routes/OverviewPage.tsx`. Add the import:

```tsx
import { useCustomizeMode } from "../state/customizeMode";
import AddPanelTile from "../components/ui/AddPanelTile";
```

Inside the component, just below the `panelIds` / `reorder` lines, add:

```tsx
  const editing = useCustomizeMode((s) => s.editing);
```

Then inside the `<div className="space-y-6">`, after the closing `})}` of the panel-map, append (still inside the `<div>`):

```tsx
          {editing && <AddPanelTile />}
```

The full file should now read:

```tsx
import { useState } from "react";
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
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";

import type { Timeframe } from "../api";
import { PANELS_BY_ID } from "../lib/panelRegistry";
import { useCustomizeMode } from "../state/customizeMode";
import { useOverviewLayout } from "../state/overviewLayout";
import AddPanelTile from "../components/ui/AddPanelTile";
import SortablePanel from "../components/ui/SortablePanel";

export default function OverviewPage() {
  const panelIds = useOverviewLayout((s) => s.panelIds);
  const reorder = useOverviewLayout((s) => s.reorder);
  const editing = useCustomizeMode((s) => s.editing);
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function handleDragEnd(e: DragEndEvent) {
    if (e.over && e.active.id !== e.over.id) {
      reorder(e.active.id as string, e.over.id as string);
    }
  }

  if (panelIds.length === 0 && !editing) {
    return (
      <div className="text-center text-sm text-slate-500 py-20">
        Click <span className="text-slate-300">Customize</span> to add panels to your overview.
      </div>
    );
  }

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <SortableContext items={panelIds} strategy={verticalListSortingStrategy}>
        <div className="space-y-6">
          {panelIds.map((id) => {
            const def = PANELS_BY_ID[id];
            if (!def) return null;
            const Component = def.component;
            const props =
              id === "price-chart"
                ? { timeframe, onTimeframeChange: setTimeframe }
                : {};
            return (
              <SortablePanel key={id} id={id} label={def.label}>
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

(Note the `panelIds.length === 0` placeholder is now gated by `&& !editing` so the AddPanelTile shows even on an empty overview when in edit mode.)

- [ ] **Step 3: Add `Escape` to exit edit mode**

Edit `frontend/src/routes/OverviewPage.tsx`. Add an import for `useEffect`:

```tsx
import { useEffect, useState } from "react";
```

And add this `useEffect` inside the component, right after the sensors line:

```tsx
  const exit = useCustomizeMode((s) => s.exit);
  useEffect(() => {
    if (!editing) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") exit();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, exit]);
```

- [ ] **Step 4: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/AddPanelTile.tsx \
        frontend/src/routes/OverviewPage.tsx
git commit -m "feat(layout): add-panel popover + Escape exits customize mode"
```

---

## Task 9 — Manual smoke test + CLAUDE.md note

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Restart the local stack**

From the repo root:

```bash
make down && make up
```

Wait ~10 s. (No backend changes; api/worker reuse existing images, only frontend rebuilds.)

- [ ] **Step 2: Smoke test in the browser**

Open `http://localhost:5173`, log in. Verify each item — STOP if any fail and debug:

- [ ] **Topbar nav.** The 4 links `Overview · Markets · Onchain · Mempool` are visible. Click each — URL changes (`/`, `/markets`, `/onchain`, `/mempool`); active link is highlighted.
- [ ] **Overview default layout.** On `/`, you see (in order): PriceHero, PriceChart, WhaleTransfers, ExchangeFlows, SmartMoney. No Customize banner; no drag handles.
- [ ] **Markets page.** `/markets` shows: PriceChart (with timeframe selector), Derivatives, SmartMoney, OrderFlow, VolumeStructure.
- [ ] **Onchain page.** `/onchain` shows: ExchangeFlows, StablecoinSupply, OnchainVolume, NetworkActivity, WhaleTransfers.
- [ ] **Mempool page.** `/mempool` shows: Mempool, Alerts.
- [ ] **Customize button.** Visible on `/` only. NOT visible on `/markets`, `/onchain`, `/mempool`.
- [ ] **Customize toggle.** Click "Customize" on overview. Drag handles appear top-right of each panel; × buttons appear next to handles; "+ Add panel" tile appears at the bottom; the topbar button reads "Done."
- [ ] **Drag reorder.** Grab a drag handle, drop a panel above another. Order updates immediately. Refresh the page (`Cmd+R`) — order persists.
- [ ] **Remove a panel.** Click × on a panel. It disappears. Refresh — still gone.
- [ ] **Add a panel.** Click "+ Add panel" → popover lists missing panels → click one → it appears at the bottom of overview, popover closes. Refresh — still there.
- [ ] **Empty-state.** Remove all panels (×× until overview is empty WHILE in edit mode). The "+ Add panel" tile is still visible (per the gated empty-state check in Task 8). Add a panel back. Click "Done" — view returns to normal.
- [ ] **Escape exits edit mode.** Enter customize mode, press `Escape` → "Done" reverts to "Customize," handles vanish.
- [ ] **Mobile (375 px viewport, DevTools).** Topbar nav fits without overflow. Customize button is hidden. Overview shows the same panel order, no drag handles, no remove buttons. Pages still navigate.
- [ ] **Existing features still work.** Click an address in WhaleTransfers → wallet drawer opens. Live price ticker still ticks. Login/logout still works.
- [ ] **LocalStorage corruption.** Open DevTools → Application → LocalStorage → `etherscope.overviewLayout`. Replace value with `{}` (invalid). Reload. The overview should fall back to the default layout and the page must not crash.

- [ ] **Step 3: Add a CLAUDE.md note**

Edit `CLAUDE.md`. Find the existing "## UI polish" section (added by the live-chart PR) and append a second bullet under it:

```markdown
- Customizable overview ✅ React Router 4-page split (`Overview · Markets · Onchain · Mempool`); overview supports drag-to-reorder + add/remove via `dnd-kit/sortable`, persisted to LocalStorage with a versioned schema; category pages are fixed-in-code, derived from a single `lib/panelRegistry.ts`. Desktop only (`≥md`); mobile renders a clean default stack. Spec: `docs/superpowers/specs/2026-05-01-customizable-layout-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(layout): note customizable overview shipping under UI polish"
```

---

## Self-review

**Spec coverage:**
- Goal / 4-page nav: Tasks 4 + 5.
- Drag-to-reorder via dnd-kit/sortable: Task 7.
- Add/remove via popover: Task 8.
- Customize toggle visible only on Overview at `≥md`: Task 5 step 1d (`isOverview` check + `hidden md:inline-flex`) + Task 7 (drag handles only render when `editing`).
- Escape exits edit mode: Task 8 step 3.
- LocalStorage persistence with versioned schema + unknown-id pruning: Task 2.
- Panel registry as single source of truth: Task 1 + every page consumes it.
- Mobile read-only fallback: Task 5 (`hidden md:inline-flex` on Customize button) + Task 7 (drag handles gated by `editing`, which can never become `true` on mobile because the toggle is hidden).
- Default overview layout: Task 1 (`DEFAULT_OVERVIEW_LAYOUT`).
- Empty-overview placeholder: Task 6 + refined in Task 8 step 2 to remain in customize mode.
- Anchor IDs preserved (`#whales` etc.): every page renders panels inside `<section id={id}>` (Task 4) or `<SortablePanel id={id}>` (Task 7) — anchor links inside the same page still work; cross-page anchor links would need `<Link to="/onchain#whales">` plus a hash-scroll effect, which is **deferred** and noted in the spec's risks section.
- Schema-version-bump fallback: Task 2's `migrate` function.
- No backend changes: confirmed across all tasks.
- Out-of-scope items (resize, category-page customization, server-side sync): explicitly skipped.

**Placeholder scan:** none — every step has runnable code/commands.

**Type consistency:**
- `PANELS`, `PANELS_BY_ID`, `DEFAULT_OVERVIEW_LAYOUT`, `PageId`, `PanelDef` defined in Task 1 and consumed by every later task with matching names.
- `useOverviewLayout` exposes `panelIds`, `reorder(activeId, overId)`, `add(id)`, `remove(id)`, `reset()` — used identically across Tasks 6, 7, 8.
- `useCustomizeMode` exposes `editing`, `toggle()`, `exit()` — used identically in Tasks 5, 7, 8.
- `SortablePanel` props: `{ id, label, children }` — Task 7 declaration matches Task 8 usage.
- `AddPanelTile` is a no-prop component — declaration and usage match.
- `DashboardShell` renders `<Outlet />` for child routes — wired in Task 3 and consumed by Task 4's `<Route element={<DashboardShell />}>`.
- The chart `timeframe` state is local to whichever route renders `<PriceChart>` — Tasks 4 (`MarketsPage`) and 6/7/8 (`OverviewPage`). No shared global; both use `useState<Timeframe>("1h")`.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-01-customizable-layout.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
