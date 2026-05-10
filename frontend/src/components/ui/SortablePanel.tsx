import type { ReactNode } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { useT } from "../../i18n/LocaleProvider";
import { SPAN_CLASS, type PanelWidth } from "../../lib/panelRegistry";
import { useCustomizeMode } from "../../state/customizeMode";
import { useOverviewLayout } from "../../state/overviewLayout";
import ErrorBoundary from "./ErrorBoundary";
import PanelShell from "./PanelShell";

type Props = {
  id: string;
  label: string;
  width: PanelWidth;
  children: ReactNode;
};

function SizeButtons({ id, width }: { id: string; width: PanelWidth }) {
  const resize = useOverviewLayout((s) => s.resize);
  const t = useT();
  // S/M/L are universal letter abbreviations and stay in both locales.
  // "Full" varies — pulled from common.full.
  const sizes: { w: PanelWidth; label: string }[] = [
    { w: 1, label: "S" },
    { w: 2, label: "M" },
    { w: 3, label: "L" },
    { w: 4, label: t("common.full") },
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
          title={t("panel_size.resize_to", { label })}
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
      <ErrorBoundary label={label}>
        <PanelShell>{children}</PanelShell>
      </ErrorBoundary>
    </section>
  );
}
