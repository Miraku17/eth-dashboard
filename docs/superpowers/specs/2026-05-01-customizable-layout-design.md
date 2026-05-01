# Customizable Overview + 4-page Navigation — Design

**Status:** approved 2026-05-01
**Track:** UI architecture overhaul (sibling to live-chart). The
project's "v" milestones stay on the data axis; this is the first
entry under "UI polish."
**Related specs:**
- `2026-04-23-eth-analytics-dashboard-design.md` (parent)
- `2026-05-01-live-chart-ws-design.md` (sibling — also UI polish track)

## Goal

Today's dashboard is a single scrolling page with all 13 panels stacked
in a fixed order. Operators want their morning glance to feel personal:

1. The first thing they see (`/`) should be their curated picks, in the
   order they choose, with the option to add or remove panels.
2. Everything else stays one click away under a small set of category
   pages — no scrolling past unrelated panels to find what they want.
3. Customization is desktop-only, single-device, fast to ship.

Success looks like: an operator opens the dashboard, sees exactly the
panels they care about most in the order they put them, and reaches any
other panel with one click on a topbar nav link.

## Non-goals

- **Resizing panels.** No column-spans, no width sliders. Each panel
  occupies its own row at the panel's natural width. Mixed-width grid
  layouts (TradingView / Notion / react-grid-layout) are explicitly out.
- **Customizing the category pages.** Only Overview is customizable in
  v1. Markets / Onchain / Mempool render a fixed registry-derived list.
- **Cross-device layout sync.** LocalStorage only for v1; the storage
  shape is designed so a future Postgres-backed swap is a small change.
- **Mobile drag-and-drop.** On `<md` breakpoints the customize toggle is
  hidden and overview renders read-only as a single-column stack.
- **Panel favourites, pinning, or per-page customization.** "On
  overview / off overview" is the only state.
- **Server-side preferences.** No new tables, no new endpoints in v1.

## UX

### Topbar

Adds a 4-link primary nav, left of the existing right-side controls:

```
[Etherscope]   Overview · Markets · Onchain · Mempool        [Health · Logout]
```

The active link is highlighted (subtle underline + slightly brighter
text). On mobile (`<md`) the same 4 inline links remain — they fit on
narrow screens since each is one short word. No hamburger menu.

### Overview customize mode

A new "Customize" button appears in the topbar **only on the Overview
route, only at `≥md` viewport.** Clicking it toggles edit mode:

- Each panel sprouts a small drag handle (≡ icon, top-right corner) +
  an `×` remove button (top-right, next to the handle).
- An "+ Add panel" dashed-outline tile is appended after the last
  panel.
- The Customize button label switches to "Done."
- Click "Done" or press `Escape` to exit edit mode.

Outside edit mode, overview renders exactly like today — no drag
handles, no remove buttons, no extra DOM weight.

### Add panel popover

Clicking the "+ Add panel" tile opens a small popover listing every
panel NOT currently on overview:

```
┌──────────────────────┐
│ Add to overview      │
├──────────────────────┤
│ Derivatives          │
│ Smart money          │
│ Order flow           │
│ Volume structure     │
│ Stablecoin supply    │
│ Mempool              │
│ Alerts               │
└──────────────────────┘
```

Clicking a row appends that panel to the end of overview, closes the
popover, and stays in edit mode.

### Mobile

`<md` viewport: customize button hidden, drag handles and remove
buttons hidden. Overview reads `panelIds` from LocalStorage and
renders them in order as a single-column stack — read-only. The four
topbar nav links work as on desktop.

## Architecture

### File structure

```
frontend/src/
  routes/
    OverviewPage.tsx          # NEW — sortable list of registered panels
    MarketsPage.tsx           # NEW — fixed: chart, derivatives, smart money, order flow, volume structure
    OnchainPage.tsx           # NEW — fixed: flows, stablecoin, on-chain volume, network, whales
    MempoolPage.tsx           # NEW — fixed: mempool, alerts
  state/
    overviewLayout.ts         # NEW — Zustand store, persisted to LocalStorage
    customizeMode.ts          # NEW — Zustand store, in-memory boolean
  lib/
    panelRegistry.ts          # NEW — single source of truth for { id, label, component, defaultPage }
  components/
    ui/SortablePanel.tsx      # NEW — wraps a panel; drag handle + remove only render when edit mode is on
    ui/AddPanelTile.tsx       # NEW — renders only in edit mode at the bottom of overview
    Topbar.tsx                # MODIFIED — adds 4-link nav + Customize/Done toggle
  App.tsx                     # MODIFIED — replaces flat layout with React Router routes
```

### New dependencies

- `react-router-dom` — routing primitives.
- `@dnd-kit/core` + `@dnd-kit/sortable` + `@dnd-kit/utilities` —
  drag-reorder. The `/sortable` package is small (~6 KB gzipped) and
  ships keyboard-arrow reordering and touch sensors out of the box.

`zustand` is already installed (from wallet-clustering work).

No backend changes. No new env vars. No migrations.

### Panel registry

`frontend/src/lib/panelRegistry.ts` becomes the single source of truth
for which panels exist, what they're called, and where they live by
default:

```typescript
import PriceHero from "../components/PriceHero";
import PriceChart from "../components/PriceChart";
import DerivativesPanel from "../components/DerivativesPanel";
import SmartMoneyLeaderboard from "../components/SmartMoneyLeaderboard";
import OrderFlowPanel from "../components/OrderFlowPanel";
import VolumeStructurePanel from "../components/VolumeStructurePanel";
import ExchangeFlowsPanel from "../components/ExchangeFlowsPanel";
import StablecoinSupplyPanel from "../components/StablecoinSupplyPanel";
import OnchainVolumePanel from "../components/OnchainVolumePanel";
import NetworkActivityPanel from "../components/NetworkActivityPanel";
import WhaleTransfersPanel from "../components/WhaleTransfersPanel";
import MempoolPanel from "../components/MempoolPanel";
import AlertEventsPanel from "../components/AlertEventsPanel";

export type PageId = "overview" | "markets" | "onchain" | "mempool";

export type PanelDef = {
  id: string;                          // stable kebab-case ID, used as LocalStorage key value
  label: string;                       // display name (topbar add-popover, customize)
  component: React.ComponentType<any>; // the panel itself
  defaultPage: PageId;                 // home page when stored layout is empty/unknown
  homeOnly?: boolean;                  // PriceHero only makes sense on overview
};

export const PANELS: PanelDef[] = [
  { id: "price-hero",        label: "Price",            component: PriceHero,            defaultPage: "overview", homeOnly: true },
  { id: "price-chart",       label: "Chart",            component: PriceChart,           defaultPage: "markets" },
  { id: "derivatives",       label: "Derivatives",      component: DerivativesPanel,     defaultPage: "markets" },
  { id: "smart-money",       label: "Smart money",      component: SmartMoneyLeaderboard, defaultPage: "markets" },
  { id: "order-flow",        label: "Order flow",       component: OrderFlowPanel,       defaultPage: "markets" },
  { id: "volume-structure",  label: "Volume structure", component: VolumeStructurePanel, defaultPage: "markets" },
  { id: "exchange-flows",    label: "Exchange flows",   component: ExchangeFlowsPanel,   defaultPage: "onchain" },
  { id: "stablecoin-supply", label: "Stablecoin supply", component: StablecoinSupplyPanel, defaultPage: "onchain" },
  { id: "onchain-volume",    label: "On-chain volume",  component: OnchainVolumePanel,   defaultPage: "onchain" },
  { id: "network-activity",  label: "Network activity", component: NetworkActivityPanel, defaultPage: "onchain" },
  { id: "whale-transfers",   label: "Whale transfers",  component: WhaleTransfersPanel,  defaultPage: "onchain" },
  { id: "mempool",           label: "Mempool",          component: MempoolPanel,         defaultPage: "mempool" },
  { id: "alerts",            label: "Alerts",           component: AlertEventsPanel,     defaultPage: "mempool" },
];

export const PANELS_BY_ID: Record<string, PanelDef> = Object.fromEntries(
  PANELS.map((p) => [p.id, p]),
);
```

The category-page components use:

```typescript
const panelsForPage = PANELS.filter((p) => p.defaultPage === "markets");
```

(no customization, fixed registry order).

### Overview state

`frontend/src/state/overviewLayout.ts`:

```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { PANELS } from "../lib/panelRegistry";

const STORAGE_KEY = "etherscope.overviewLayout";

const DEFAULT_LAYOUT = [
  "price-hero",
  "price-chart",
  "whale-transfers",
  "exchange-flows",
  "smart-money",
];

type State = {
  version: 1;
  panelIds: string[];
  reorder: (activeId: string, overId: string) => void;
  add: (id: string) => void;
  remove: (id: string) => void;
  reset: () => void;
};

export const useOverviewLayout = create<State>()(
  persist(
    (set) => ({
      version: 1,
      panelIds: DEFAULT_LAYOUT,
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
      reset: () => set((s) => ({ ...s, panelIds: DEFAULT_LAYOUT })),
    }),
    {
      name: STORAGE_KEY,
      version: 1,
      // On load, drop any IDs that aren't in the registry (panel was
      // removed from the codebase). Drop unknown versions.
      migrate: (persisted: any) => {
        if (!persisted || persisted.version !== 1) {
          return { version: 1, panelIds: DEFAULT_LAYOUT };
        }
        const known = new Set(PANELS.map((p) => p.id));
        const cleaned = (persisted.panelIds ?? []).filter((id: string) => known.has(id));
        return { ...persisted, panelIds: cleaned.length > 0 ? cleaned : DEFAULT_LAYOUT };
      },
    },
  ),
);
```

`customizeMode.ts` is a trivial in-memory store:

```typescript
import { create } from "zustand";

type State = { editing: boolean; toggle: () => void; exit: () => void };

export const useCustomizeMode = create<State>((set) => ({
  editing: false,
  toggle: () => set((s) => ({ editing: !s.editing })),
  exit: () => set({ editing: false }),
}));
```

`OverviewPage` registers an `Escape` keydown listener that calls `exit()`
while editing.

### Routing

`App.tsx` becomes:

```tsx
<AuthGate>
  <BrowserRouter>
    <DashboardShell>
      <Routes>
        <Route index element={<OverviewPage />} />
        <Route path="markets" element={<MarketsPage />} />
        <Route path="onchain" element={<OnchainPage />} />
        <Route path="mempool" element={<MempoolPage />} />
      </Routes>
    </DashboardShell>
  </BrowserRouter>
  <WalletDrawer />
</AuthGate>
```

`<DashboardShell>` extracts what's currently around the panels —
`<Topbar />`, `<main className="mx-auto max-w-...">`, the footer.
Each route's content renders inside `<Outlet />`.

The chart's `timeframe` state currently lives in `App.tsx` (line 42).
It moves to `MarketsPage` (where `<PriceChart>` is rendered as a
category-page panel) and to `OverviewPage` (when chart is on overview).
Both are local `useState` — no shared global. The `1h / 4h / 1d`
selector exists per-instance and that's fine for v1; if a user wants
synchronized timeframe across views, that's a v2 ask.

### Drag-reorder

`OverviewPage.tsx` wraps its panel list in a dnd-kit `<DndContext>` +
`<SortableContext>`:

```tsx
const ids = useOverviewLayout((s) => s.panelIds);
const reorder = useOverviewLayout((s) => s.reorder);
const editing = useCustomizeMode((s) => s.editing);

return (
  <DndContext
    onDragEnd={(e) => {
      if (e.active.id !== e.over?.id) {
        reorder(e.active.id as string, e.over!.id as string);
      }
    }}
  >
    <SortableContext items={ids} strategy={verticalListSortingStrategy}>
      <div className="space-y-6">
        {ids.map((id) => (
          <SortablePanel key={id} id={id} editing={editing} />
        ))}
        {editing && <AddPanelTile />}
      </div>
    </SortableContext>
  </DndContext>
);
```

`<SortablePanel>` uses `useSortable({ id })` to get drag bindings; only
attaches them when `editing` is true. The drag handle is a small
absolute-positioned button in the top-right; outside edit mode the
handle is removed from the DOM entirely.

### Add-panel popover

`<AddPanelTile>` is a dashed-outline tile that, on click, opens a
`<Popover>` (already part of the design system if any; otherwise a
bespoke absolute-positioned `<div>` with click-outside dismissal).
Lists `PANELS.filter(p => !panelIds.includes(p.id))` in registry order.
Click a row → `add(id)` and close popover.

### Customize button placement

Lives in the topbar's right cluster. Visible only when:
- `useLocation().pathname === "/"` (overview), AND
- viewport ≥ md (Tailwind `md:` prefix on the wrapper).

Clicking calls `useCustomizeMode().toggle()`. Label is "Customize"
when not editing, "Done" when editing.

## Edge cases

- **Empty overview** — `panelIds.length === 0`. Render a centred
  placeholder "Click 'Customize' to add panels to your overview."
  Keep customize button visible regardless.
- **Duplicate add** — `add(id)` is a no-op when `id` is already in
  the list. Add-popover row is hidden for already-present IDs by
  filtering, so the path is rarely hit.
- **Unknown stored ID** — handled in the `migrate` callback above.
- **Schema-version bump** — unknown `version` falls back to default
  layout. The current schema is v1; future changes increment.
- **Panel referenced by overview AND a category page** — legal. Two
  independent React mounts, each with its own state (e.g. chart
  timeframe). Acceptable for v1; consolidate via shared context if
  it becomes a problem.
- **Mobile in edit mode** — impossible by construction (button
  hidden), but if `editing === true` somehow persists across a resize
  to mobile, the page renders normally without drag handles. The
  store carries the `editing` boolean across resizes; we don't reset
  it on resize.
- **Refresh during edit mode** — `editing` is in-memory, so a refresh
  drops you back to read-only. The custom layout persists. This is
  desired — refresh is an implicit "Done."

## Persistence shape (LocalStorage v1)

```json
{
  "state": {
    "version": 1,
    "panelIds": ["price-hero", "price-chart", "whale-transfers", "exchange-flows", "smart-money"]
  },
  "version": 1
}
```

(Outer `version` is Zustand persist middleware's; inner `version` is
ours.)

Future migration to Postgres: add a `user_preferences` table, swap the
`persist` middleware for a thin async loader/saver hitting
`/api/preferences`. The storage shape stays the same so existing
clients keep working through the cutover.

## Testing

Frontend has no vitest infra (per earlier session decisions). Validation
strategy:

- `npm run build` — type-checks the whole codebase. Must pass.
- Manual smoke checklist (in the implementation plan):
  - Drag-reorder persists across reload.
  - Add a panel — appears at end, persists across reload.
  - Remove a panel — disappears, persists across reload.
  - Empty overview shows placeholder; "Customize" still works.
  - Mobile (375 px) shows clean stack, no drag handles, no customize
    button.
  - Each of the four nav links lands on a page with the expected panels.
  - Anchor IDs (`#whales`, `#derivatives`, etc.) on category pages
    still scroll to the right panel.
  - LocalStorage corruption test: paste invalid JSON for the storage
    key, reload — falls back to default layout cleanly.

Backend: zero changes. Existing test suite must stay green.

## Implementation milestones

Approximate ordering — the writing-plans pass will refine each into
TDD-shaped tasks:

1. Install router + dnd-kit. Set up the panel registry + page-id
   types.
2. Extract `<DashboardShell>` from `App.tsx`. Wire up `<BrowserRouter>`
   with a single Overview route that mirrors today's layout (sanity
   step — no behaviour change yet).
3. Add the three category routes (Markets / Onchain / Mempool). Each
   renders `PANELS.filter(...)` in fixed order.
4. Update Topbar: 4-link nav with active highlighting; mobile hamburger
   for navigation only (Customize button is only desktop).
5. Build the overview layout store + customize-mode store. Replace
   the Overview route's content with the registry-driven mapped list.
   No drag yet — just registry-driven render.
6. Wire dnd-kit: SortablePanel wrapper, drag handle, drag-end calls
   `reorder()`. Behind `editing` flag.
7. Customize button in Topbar: toggles `editing`. Add the × remove
   button on each panel + the "+ Add panel" tile + popover.
8. Mobile fallback: hide customize button on `<md`; hide drag handles
   and remove buttons regardless of editing state.
9. Update CLAUDE.md note under "## UI polish".

## Risks and known limits

- **Panel components and module-level state** — some panels keep
  state in `useRef` or singleton modules (e.g. the chart's WS
  subscription via the `binanceWS` singleton). Mounting the same
  panel on overview AND on a category page means two subscribers to
  the same trade stream. The WS singleton is reference-counted so
  this is fine, but worth noting.
- **Anchor scrolling vs route changes** — today, clicking a Topbar
  shortcut to `#whales` scrolls within the current page. With
  routing, anchor links across pages need `<Link to="/onchain#whales">`
  + a small effect on the Onchain route that scrolls to the hash on
  mount. Implementation plan must handle this if Topbar's shortcut
  list is preserved.
- **First-paint shift** — the Zustand persist middleware is
  synchronous against LocalStorage, so first paint sees the user's
  layout. No flash-of-default needed.
- **dnd-kit + React 18 strict mode** — works fine; no known
  compatibility issues.

## Out of scope (v2 candidates)

- Resizing panels.
- Customizing category pages (drag-reorder there too).
- Cross-device layout sync via Postgres.
- Panel pinning, favouriting, or per-page custom defaults.
- A "Reset to default" button (the store already exposes `reset()`;
  surfacing it is one line of JSX, but it's not in v1).
- Synchronized chart timeframe across overview and Markets pages.
- Per-page customize toggle in the topbar (today: only Overview is
  customizable, so the toggle only appears there).
