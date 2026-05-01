import type { ComponentType } from "react";

import AlertEventsPanel from "../components/AlertEventsPanel";
import DerivativesPanel from "../components/DerivativesPanel";
import ExchangeFlowsPanel from "../components/ExchangeFlowsPanel";
import MempoolPanel from "../components/MempoolPanel";
import NetworkActivityPanel from "../components/NetworkActivityPanel";
import OnchainVolumePanel from "../components/OnchainVolumePanel";
import OrderFlowPanel from "../components/OrderFlowPanel";
import PriceChart from "../components/PriceChart";
import PriceHero from "../components/PriceHero";
import SmartMoneyLeaderboard from "../components/SmartMoneyLeaderboard";
import StablecoinSupplyPanel from "../components/StablecoinSupplyPanel";
import VolumeStructurePanel from "../components/VolumeStructurePanel";
import WhaleTransfersPanel from "../components/WhaleTransfersPanel";

export type PageId = "overview" | "markets" | "onchain" | "mempool";

export type PanelDef = {
  /** Stable kebab-case id; persisted to LocalStorage and used as drag id. */
  id: string;
  /** Display name in the customize popover and topbar nav. */
  label: string;
  /** The panel component. May accept zero props or panel-specific props. */
  component: ComponentType<any>;
  /** Page this panel belongs to when not on overview. */
  defaultPage: PageId;
  /** True for panels that only make sense on overview (PriceHero). */
  homeOnly?: boolean;
};

export const PANELS: PanelDef[] = [
  { id: "price-hero", label: "Price", component: PriceHero, defaultPage: "overview", homeOnly: true },
  { id: "price-chart", label: "Chart", component: PriceChart, defaultPage: "markets" },
  { id: "derivatives", label: "Derivatives", component: DerivativesPanel, defaultPage: "markets" },
  { id: "smart-money", label: "Smart money", component: SmartMoneyLeaderboard, defaultPage: "markets" },
  { id: "order-flow", label: "Order flow", component: OrderFlowPanel, defaultPage: "markets" },
  { id: "volume-structure", label: "Volume structure", component: VolumeStructurePanel, defaultPage: "markets" },
  { id: "exchange-flows", label: "Exchange flows", component: ExchangeFlowsPanel, defaultPage: "onchain" },
  { id: "stablecoin-supply", label: "Stablecoin supply", component: StablecoinSupplyPanel, defaultPage: "onchain" },
  { id: "onchain-volume", label: "On-chain volume", component: OnchainVolumePanel, defaultPage: "onchain" },
  { id: "network-activity", label: "Network activity", component: NetworkActivityPanel, defaultPage: "onchain" },
  { id: "whale-transfers", label: "Whale transfers", component: WhaleTransfersPanel, defaultPage: "onchain" },
  { id: "mempool", label: "Mempool", component: MempoolPanel, defaultPage: "mempool" },
  { id: "alerts", label: "Alerts", component: AlertEventsPanel, defaultPage: "mempool" },
];

export const PANELS_BY_ID: Record<string, PanelDef> = Object.fromEntries(
  PANELS.map((p) => [p.id, p]),
);

/** Default panels on the overview when no customization has happened yet. */
export const DEFAULT_OVERVIEW_LAYOUT: string[] = [
  "price-hero",
  "price-chart",
  "whale-transfers",
  "exchange-flows",
  "smart-money",
];
