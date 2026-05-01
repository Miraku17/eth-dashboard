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
