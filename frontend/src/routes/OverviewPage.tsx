import { useState, type ReactNode } from "react";

import type { Timeframe } from "../api";
import AlertEventsPanel from "../components/AlertEventsPanel";
import DerivativesPanel from "../components/DerivativesPanel";
import ExchangeFlowsPanel from "../components/ExchangeFlowsPanel";
import MempoolPanel from "../components/MempoolPanel";
import NetworkActivityPanel from "../components/NetworkActivityPanel";
import OnchainVolumePanel from "../components/OnchainVolumePanel";
import OrderFlowPanel from "../components/OrderFlowPanel";
import PriceChart from "../components/PriceChart";
import SmartMoneyLeaderboard from "../components/SmartMoneyLeaderboard";
import PriceHero from "../components/PriceHero";
import StablecoinSupplyPanel from "../components/StablecoinSupplyPanel";
import VolumeStructurePanel from "../components/VolumeStructurePanel";
import WhaleTransfersPanel from "../components/WhaleTransfersPanel";
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
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  return (
    <>
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
    </>
  );
}
