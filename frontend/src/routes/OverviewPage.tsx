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
