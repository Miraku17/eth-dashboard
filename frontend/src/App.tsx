import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchHealth, type Timeframe } from "./api";
import PriceChart from "./components/PriceChart";
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
      <PriceChart timeframe={timeframe} />
    </main>
  );
}
