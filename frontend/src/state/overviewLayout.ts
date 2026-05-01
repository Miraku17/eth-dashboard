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
