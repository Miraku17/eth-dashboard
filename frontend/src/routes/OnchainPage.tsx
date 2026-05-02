import type { ReactNode } from "react";

import { ONCHAIN_SECTIONS, PANELS, type OnchainSection } from "../lib/panelRegistry";
import ErrorBoundary from "../components/ui/ErrorBoundary";
import PanelShell from "../components/ui/PanelShell";

function Guarded({
  label,
  children,
  id,
}: {
  label: string;
  children: ReactNode;
  id?: string;
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <ErrorBoundary label={label}>
        <PanelShell>{children}</PanelShell>
      </ErrorBoundary>
    </section>
  );
}

const PANELS_FOR_PAGE = PANELS.filter((p) => p.defaultPage === "onchain");

// Group once at module load. Panels without a section fall into a final
// "Other" bucket so anything new stays visible until it's tagged.
type Group = {
  id: OnchainSection | "uncategorized";
  label: string;
  panels: typeof PANELS_FOR_PAGE;
};

function groupBySection(): Group[] {
  const groups: Group[] = ONCHAIN_SECTIONS.map((s) => ({
    id: s.id,
    label: s.label,
    panels: PANELS_FOR_PAGE.filter((p) => p.section === s.id),
  }));
  const uncategorized = PANELS_FOR_PAGE.filter((p) => !p.section);
  if (uncategorized.length > 0) {
    groups.push({ id: "uncategorized", label: "Other", panels: uncategorized });
  }
  return groups.filter((g) => g.panels.length > 0);
}

const GROUPS = groupBySection();

export default function OnchainPage() {
  return (
    <div className="space-y-8">
      {GROUPS.map((group) => (
        <section key={group.id} className="space-y-4">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400 border-b border-surface-divider pb-2">
            {group.label}
          </h2>
          {group.panels.map((p) => {
            const Component = p.component;
            return (
              <Guarded key={p.id} label={p.label} id={p.id}>
                <Component />
              </Guarded>
            );
          })}
        </section>
      ))}
    </div>
  );
}
