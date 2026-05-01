import { useState, type ReactNode } from "react";

import type { Timeframe } from "../api";
import { PANELS } from "../lib/panelRegistry";
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

const PANELS_FOR_PAGE = PANELS.filter((p) => p.defaultPage === "markets");

export default function MarketsPage() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  return (
    <>
      {PANELS_FOR_PAGE.map((p) => {
        const Component = p.component;
        const props =
          p.id === "price-chart"
            ? { timeframe, onTimeframeChange: setTimeframe }
            : {};
        return (
          <Guarded key={p.id} label={p.label} id={p.id}>
            <Component {...props} />
          </Guarded>
        );
      })}
    </>
  );
}
