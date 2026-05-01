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
