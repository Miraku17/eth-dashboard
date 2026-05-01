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
  const exit = useCustomizeMode((s) => s.exit);
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  // Escape key exits customize mode.
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

  // Empty overview placeholder, but only when NOT in edit mode — in edit mode
  // we still want the AddPanelTile visible so the user can add their first panel.
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
