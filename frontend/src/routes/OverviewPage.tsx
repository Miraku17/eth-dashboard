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
