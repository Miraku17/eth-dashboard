import { useEffect, useRef, useState } from "react";

import { PANELS } from "../../lib/panelRegistry";
import { useOverviewLayout } from "../../state/overviewLayout";

/**
 * Floating "Add panel" button.
 *
 * Renders as a fixed-position circular FAB in the bottom-right of the
 * viewport so it's always reachable while the user is in customize mode —
 * no need to scroll to the bottom of a tall overview to find it.
 *
 * The popover opens upward (and right-aligned to the FAB) so it stays
 * inside the viewport regardless of how tall the overview is.
 */
export default function AddPanelTile() {
  const panels = useOverviewLayout((s) => s.panels);
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

  // Esc closes the popover too — standard interaction for floating menus.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const presentIds = new Set(panels.map((p) => p.id));
  const available = PANELS.filter((p) => !presentIds.has(p.id));

  return (
    <div
      ref={wrapperRef}
      className="fixed bottom-6 right-6 z-30"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Add panel"
        aria-expanded={open}
        title="Add panel"
        className={
          "group flex h-14 w-14 items-center justify-center rounded-full bg-brand text-white shadow-lg shadow-black/40 ring-1 ring-brand-soft/30 transition " +
          "hover:bg-brand-soft hover:scale-105 active:scale-95 " +
          (open ? "ring-2 ring-brand-soft" : "")
        }
      >
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={"transition-transform " + (open ? "rotate-45" : "")}
          aria-hidden="true"
        >
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>

      {open && (
        <div
          className="absolute bottom-full right-0 mb-3 w-72 max-h-[60vh] overflow-y-auto rounded-lg border border-surface-border bg-surface-card shadow-card p-2"
        >
          <div className="text-[10px] font-semibold tracking-widest text-slate-500 uppercase px-2 py-1.5">
            Add to overview
          </div>
          {available.length === 0 ? (
            <div className="px-3 py-2 text-xs text-slate-500">
              All panels are on overview.
            </div>
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
