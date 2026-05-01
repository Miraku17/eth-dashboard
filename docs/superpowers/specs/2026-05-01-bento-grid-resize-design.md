# Bento-grid Resize for Overview — Design

**Status:** approved 2026-05-01
**Track:** UI polish (extends `2026-05-01-customizable-layout-design.md`)
**Related specs:**
- `2026-05-01-customizable-layout-design.md` (parent — drag/reorder + add/remove)
- `2026-04-23-eth-analytics-dashboard-design.md` (root)

## Goal

The customizable Overview shipped with all panels at full row width. The
operator wants a **bento-grid look**: panels at varied discrete widths
(narrow, medium, wide, full) so the page composes like Apple's product
pages or CoinMarketCap's dashboard rather than a tall single-column
stack.

This spec adds **discrete column-span sizing** to each panel on the
Overview, controlled in customize mode via four size buttons (S / M /
L / Full). Reorder, add, and remove from the parent spec all keep
working unchanged.

## Non-goals

- **Free-form pixel-arbitrary resize.** No corner drag handles, no
  `react-grid-layout`. Bento is a small palette, not a CAD tool.
- **Custom row heights.** Each panel renders at its natural content
  height; the grid only governs column spans.
- **Resize on category pages.** Markets / Onchain / Mempool stay
  fixed-in-code (same as parent spec).
- **Mobile resize.** On `<md` breakpoints widths are ignored; every
  panel renders full-width as today.
- **Breakpoint-specific widths.** A panel has ONE stored width; CSS
  collapses spans on narrower viewports automatically (see "Grid
  behaviour" below).

## UX

### Edit mode

Inside the existing customize-mode floating handle cluster (currently
`⋮⋮ ×` in `<SortablePanel>`'s top-right), insert a 4-button size
selector to the LEFT of the drag handle:

```
[ S | M | L | Full ]   ⋮⋮   ×
```

Each segment is a small button (~22px wide). The currently-active size
is highlighted (filled background); the others are dim. Click any
button to switch — the panel reflows immediately, persisted to
LocalStorage.

Outside edit mode, the cluster (and therefore the size selector) is
not rendered — exactly like today.

### Read mode (non-edit)

Panels render at their stored width. The grid container is a 4-column
CSS grid; each panel applies `col-span-{width}` so a "L" (3) panel
occupies three of four columns and an "S" (1) panel occupies one. The
next panel flows into the remaining slot if it fits, else wraps to a
new row. Empty slots in a row are simply unused space — we don't auto-
fill or rearrange.

### Mobile (`<md`)

Width is ignored. Container collapses to `grid-cols-1`; every panel
spans the full width. The customize button is also hidden (already
true from the parent spec), so nothing to do there.

## Grid behaviour

The Overview's container element changes from `space-y-6` (vertical
stack) to:

```html
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
```

Per panel, the column span uses Tailwind's `col-span-N` with safelist-
friendly literals (no dynamic class names — the `safelist` either lists
all 4 spans, or the registry pre-resolves them to literal class strings):

```typescript
const SPAN_CLASS: Record<1|2|3|4, string> = {
  1: "col-span-1",
  2: "col-span-1 md:col-span-2",
  3: "col-span-1 md:col-span-2 lg:col-span-3",
  4: "col-span-1 md:col-span-2 lg:col-span-3 xl:col-span-4",
};
```

This map is the trick that makes "ONE stored width" sensible across
breakpoints: a panel set to "L" (3 cols at xl) renders correctly at
every smaller viewport — collapsing to 3-of-3 at lg, 2-of-2 at md,
1-of-1 at sm. No breakpoint-specific UI needed.

Mapping rationale:
- A panel marked "Full" (4) always fills the row at xl, but at lg it's
  3-of-3 (still the whole row), at md it's 2-of-2, at sm it's full —
  i.e. always the whole row.
- A panel marked "L" (3) fills the row at lg and below, but at xl
  leaves a 1-col slot for an S panel beside it.
- "M" (2) is half-width at xl, half at lg (with a 1-col gap), full at
  md, full at sm.
- "S" (1) is quarter-width at xl, third at lg, half at md, full at sm.

## Architecture

### Stored shape (LocalStorage)

Today's v1 shape:

```json
{ "version": 1, "panelIds": ["price-hero", "price-chart", ...] }
```

Becomes v2:

```json
{
  "version": 2,
  "panels": [
    { "id": "price-hero", "width": 4 },
    { "id": "price-chart", "width": 3 },
    { "id": "exchange-flows", "width": 1 },
    { "id": "whale-transfers", "width": 2 }
  ]
}
```

The `migrate(persisted, fromVersion)` function in `overviewLayout.ts`:
- `fromVersion === 1`: map each `panelIds[i]` to `{ id, width: PANELS_BY_ID[id].defaultWidth ?? 4 }`. Preserves order; gives every existing user a sensible bento-ified layout on first load.
- `fromVersion === 2`: prune entries whose `id` isn't in the registry; if every entry was pruned, fall back to `DEFAULT_OVERVIEW_LAYOUT`.
- Anything else: fall back to default.

### Registry change

`lib/panelRegistry.ts` gains a `defaultWidth` field per panel:

```typescript
export type PanelWidth = 1 | 2 | 3 | 4;

export type PanelDef = {
  id: string;
  label: string;
  component: ComponentType<any>;
  defaultPage: PageId;
  defaultWidth: PanelWidth;     // NEW
  homeOnly?: boolean;
};
```

Sensible defaults per panel (designer judgment, easy to tune later):

| Panel | Default width |
|---|---|
| price-hero | 4 (Full) |
| price-chart | 3 (L) |
| whale-transfers | 2 (M) |
| exchange-flows | 1 (S) |
| smart-money | 2 (M) |
| derivatives | 2 (M) |
| order-flow | 2 (M) |
| volume-structure | 2 (M) |
| stablecoin-supply | 1 (S) |
| onchain-volume | 2 (M) |
| network-activity | 2 (M) |
| mempool | 2 (M) |
| alerts | 2 (M) |

The new `DEFAULT_OVERVIEW_LAYOUT` becomes:

```typescript
export const DEFAULT_OVERVIEW_LAYOUT: { id: string; width: PanelWidth }[] = [
  { id: "price-hero", width: 4 },
  { id: "price-chart", width: 3 },
  { id: "exchange-flows", width: 1 },
  { id: "whale-transfers", width: 2 },
  { id: "smart-money", width: 2 },
];
```

### Store API change

`useOverviewLayout` exposes (changes from parent spec):

```typescript
type Stored = { id: string; width: PanelWidth };

type State = {
  version: 2;
  panels: Stored[];
  reorder: (activeId: string, overId: string) => void;   // unchanged signature
  add: (id: string, width?: PanelWidth) => void;          // width defaults to registry's defaultWidth
  remove: (id: string) => void;                           // unchanged
  resize: (id: string, width: PanelWidth) => void;        // NEW
  reset: () => void;                                      // unchanged
};
```

Consumers that previously read `panelIds: string[]` now read `panels: Stored[]` and pull `id` / `width` per entry.

### `<SortablePanel>` changes

- New optional prop `width: PanelWidth`.
- The wrapping `<section>` adds `className={SPAN_CLASS[width]}` (in addition to its existing `scroll-mt-20 relative`).
- The edit-mode handle cluster gets a new `<SizeButtons>` sub-component to the LEFT of the drag handle.

### `<SizeButtons>` (new sub-component, file-internal to `SortablePanel.tsx`)

```tsx
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
```

## Reorder semantics

`reorder(activeId, overId)` keeps each panel's stored `width`. Dragging
a panel re-positions it; its size doesn't change. Implementation in the
store mirrors today's reorder, just over the `panels` array instead of
`panelIds`.

## Add / remove semantics

- `add(id)` appends `{ id, width: PANELS_BY_ID[id]?.defaultWidth ?? 4 }` to `panels` if not already present.
- `remove(id)` filters by id. Same as today.

## Edge cases

- **Reflow gaps.** If a row has, e.g., a "L" + "S" + "S" sequence, the L claims 3 cols and the next two S panels claim 1 col each on the next row at xl (since L+S = 4 cols already). At lg this becomes L=3 alone on row 1, S+S+? on row 2. Operators may see whitespace at certain panel-count combos — that's intentional (it's bento, not auto-flow). They can drag-reorder to compose tighter.
- **Migration from v1 with unknown panel IDs.** Filter unknowns BEFORE applying defaults; if everything is unknown, fall back to `DEFAULT_OVERVIEW_LAYOUT`.
- **Schema-version bump.** Bumping to v3 in the future works the same way: each migration step transforms shape; an unknown version → default.
- **Width applied with a registry that doesn't carry `defaultWidth`** (e.g. mid-deploy with a stale build): the migrate function nullish-coalesces to 4 (Full). No crash.
- **Single-column on `<md`.** Tailwind's `grid-cols-1` overrides every `col-span-N` in the SPAN_CLASS strings — at sm/xs the spans flatten to 1 because the parent only has 1 col. (CSS Grid clamps `grid-column: span N` to the available track count.)

## Tests

Frontend: still no vitest. Validation = `npm run build` + extended manual smoke checklist:

- Default layout shows the 5 default panels at their default widths (PriceHero Full, Chart L, Flows S, Whales M, SmartMoney M).
- Click S/M/L/Full on any panel → panel reflows immediately; refresh → width persists.
- Migration from v1: clear LocalStorage, set the v1 shape manually, reload — every panel takes its `defaultWidth`; layout renders.
- Adding a panel via the popover gives it its `defaultWidth`.
- Reorder doesn't change widths.
- xl viewport (≥1280px): up to 4-col layouts work. lg (1024–1279): widths collapse to 3-col max. md (768–1023): collapses to 2-col max. sm (<768): everything full-width.
- LocalStorage corruption falls back to default cleanly (test by pasting `{}` into the storage key).

Backend: no changes.

## Implementation milestones

(Refined in the writing-plans pass.)

1. Registry: add `defaultWidth` field + `PanelWidth` type. Bump `DEFAULT_OVERVIEW_LAYOUT` to the new `{ id, width }[]` shape.
2. Store: bump schema to v2; replace `panelIds` with `panels`; add `resize()`; rewrite `migrate()` to handle v1 → v2.
3. `<SortablePanel>`: accept `width` prop, apply `SPAN_CLASS[width]`, render `<SizeButtons>` in edit mode.
4. `OverviewPage.tsx`: container becomes a 4-col grid; iterate over `panels` instead of `panelIds`; pass `width` to `<SortablePanel>`.
5. `<AddPanelTile>`: account for the v2 shape (`panels.find(p => p.id === id)` instead of `panelIds.includes(id)`).
6. CLAUDE.md: append "+ resize" to the customizable-overview line.
7. Manual smoke pass against the checklist above.

## Risks and known limits

- **Empty cells.** When the row's used columns + the next panel's width exceeds 4, that panel wraps and the previous row has a gap. This is bento by design, but operators may find it visually noisy if their panel mix doesn't compose cleanly. They can fix by reordering or resizing.
- **Tailwind purging.** Static `SPAN_CLASS` literal strings are safelist-friendly — Tailwind's PurgeCSS sees them at build time. No `safelist` config needed because the strings appear verbatim in source.
- **First-paint shift.** None expected — Zustand persist is sync, so the migration runs before first render.
- **Cross-device sync.** Still LocalStorage-only. Future Postgres swap will need a `version: 2` payload — designed-in.

## Future work (not v2)

- A "Reset bento" button to return all widths to their defaults without losing the panel set.
- Drag-resize handles for finer control (only if the discrete sizes prove too rigid in practice).
- Per-page custom layouts (Markets / Onchain / Mempool also customizable).
- Cross-device sync via Postgres.
