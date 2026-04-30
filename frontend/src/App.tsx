import { useState, type ReactNode } from "react";

import type { Timeframe } from "./api";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts";
import AlertEventsPanel from "./components/AlertEventsPanel";
import DerivativesPanel from "./components/DerivativesPanel";
import ExchangeFlowsPanel from "./components/ExchangeFlowsPanel";
import MempoolPanel from "./components/MempoolPanel";
import NetworkActivityPanel from "./components/NetworkActivityPanel";
import OnchainVolumePanel from "./components/OnchainVolumePanel";
import OrderFlowPanel from "./components/OrderFlowPanel";
import PriceChart from "./components/PriceChart";
import SmartMoneyLeaderboard from "./components/SmartMoneyLeaderboard";
import PriceHero from "./components/PriceHero";
import StablecoinSupplyPanel from "./components/StablecoinSupplyPanel";
import Topbar from "./components/Topbar";
import VolumeStructurePanel from "./components/VolumeStructurePanel";
import WhaleTransfersPanel from "./components/WhaleTransfersPanel";
import AuthGate from "./components/AuthGate";
import ErrorBoundary from "./components/ui/ErrorBoundary";

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
    // `scroll-mt-20` offsets the sticky topbar so anchor jumps don't hide
    // the top edge of the panel behind it.
    <section id={id} className="scroll-mt-20">
      <ErrorBoundary label={label}>{children}</ErrorBoundary>
    </section>
  );
}

export default function App() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  useGlobalShortcuts();

  return (
    <AuthGate>
      <div className="min-h-screen">
        <Topbar />
      <main className="mx-auto max-w-[1600px] px-4 sm:px-6 py-6 space-y-6">
        <Guarded label="Price" id="overview">
          <PriceHero />
        </Guarded>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2">
            <Guarded label="Chart">
              <PriceChart timeframe={timeframe} onTimeframeChange={setTimeframe} />
            </Guarded>
          </div>
          <div className="space-y-6">
            <Guarded label="Exchange flows" id="flows">
              <ExchangeFlowsPanel />
            </Guarded>
            <Guarded label="Stablecoin supply">
              <StablecoinSupplyPanel />
            </Guarded>
          </div>
        </div>

        <Guarded label="Derivatives" id="derivatives">
          <DerivativesPanel />
        </Guarded>
        <Guarded label="Smart money" id="smart-money">
          <SmartMoneyLeaderboard />
        </Guarded>
        <Guarded label="Order flow" id="order-flow">
          <OrderFlowPanel />
        </Guarded>
        <Guarded label="Volume structure" id="volume-structure">
          <VolumeStructurePanel />
        </Guarded>
        <Guarded label="Network activity">
          <NetworkActivityPanel />
        </Guarded>
        <Guarded label="On-chain volume">
          <OnchainVolumePanel />
        </Guarded>
        <Guarded label="Whale transfers" id="whales">
          <WhaleTransfersPanel />
        </Guarded>
        <Guarded label="Mempool" id="mempool">
          <MempoolPanel />
        </Guarded>
        <Guarded label="Alerts" id="alerts">
          <AlertEventsPanel />
        </Guarded>

        <footer className="pt-4 pb-6 text-center text-[11px] text-slate-600">
          Data: Binance · Dune Analytics · Alchemy · Etherscan · CoinGecko
        </footer>
      </main>
    </div>
    </AuthGate>
  );
}
