import { useState } from "react";

import type { Timeframe } from "./api";
import AlertEventsPanel from "./components/AlertEventsPanel";
import ExchangeFlowsPanel from "./components/ExchangeFlowsPanel";
import OnchainVolumePanel from "./components/OnchainVolumePanel";
import PriceChart from "./components/PriceChart";
import PriceHero from "./components/PriceHero";
import StablecoinSupplyPanel from "./components/StablecoinSupplyPanel";
import Topbar from "./components/Topbar";
import WhaleTransfersPanel from "./components/WhaleTransfersPanel";

export default function App() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="mx-auto max-w-[1600px] px-6 py-6 space-y-6">
        <PriceHero />

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2">
            <PriceChart timeframe={timeframe} onTimeframeChange={setTimeframe} />
          </div>
          <div className="space-y-6">
            <ExchangeFlowsPanel />
            <StablecoinSupplyPanel />
          </div>
        </div>

        <OnchainVolumePanel />
        <WhaleTransfersPanel />
        <AlertEventsPanel />

        <footer className="pt-4 pb-6 text-center text-[11px] text-slate-600">
          Data: Binance · Dune Analytics · Alchemy · Etherscan · CoinGecko
        </footer>
      </main>
    </div>
  );
}
