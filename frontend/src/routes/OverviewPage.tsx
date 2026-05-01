import { useState, type ReactNode } from "react";

import type { Timeframe } from "../api";
import { PANELS_BY_ID } from "../lib/panelRegistry";
import { useOverviewLayout } from "../state/overviewLayout";
import ErrorBoundary from "../components/ui/ErrorBoundary";

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
      <ErrorBoundary label={label}>{children}</ErrorBoundary>
    </section>
  );
}

export default function OverviewPage() {
  const panelIds = useOverviewLayout((s) => s.panelIds);
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  if (panelIds.length === 0) {
    return (
      <div className="text-center text-sm text-slate-500 py-20">
        Click <span className="text-slate-300">Customize</span> to add panels to your overview.
      </div>
    );
  }

  return (
    <>
      {panelIds.map((id) => {
        const def = PANELS_BY_ID[id];
        if (!def) return null;
        const Component = def.component;
        const props =
          id === "price-chart"
            ? { timeframe, onTimeframeChange: setTimeframe }
            : {};
        return (
          <Guarded key={id} label={def.label} id={id}>
            <Component {...props} />
          </Guarded>
        );
      })}
    </>
  );
}
