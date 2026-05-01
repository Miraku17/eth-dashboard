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
