import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchHealth, type Timeframe } from "./api";
import ExchangeFlowsPanel from "./components/ExchangeFlowsPanel";
import OnchainVolumePanel from "./components/OnchainVolumePanel";
import PriceChart from "./components/PriceChart";
import StablecoinSupplyPanel from "./components/StablecoinSupplyPanel";
import TimeframeSelector from "./components/TimeframeSelector";

export default function App() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  return (
    <main className="min-h-screen p-8 space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Eth Analytics</h1>
        {health && (
          <span className="text-xs text-neutral-500">
            api: {health.status} (v{health.version})
          </span>
        )}
      </header>
      <div className="flex items-center gap-4">
        <TimeframeSelector value={timeframe} onChange={setTimeframe} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <PriceChart timeframe={timeframe} />
        </div>
        <div className="space-y-6">
          <ExchangeFlowsPanel />
          <StablecoinSupplyPanel />
        </div>
      </div>
      <OnchainVolumePanel />
    </main>
  );
}
