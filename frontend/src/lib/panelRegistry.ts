import type { ComponentType } from "react";

import AlertEventsPanel from "../components/AlertEventsPanel";
import DerivativesPanel from "../components/DerivativesPanel";
import ExchangeFlowsPanel from "../components/ExchangeFlowsPanel";
import LstMarketSharePanel from "../components/LstMarketSharePanel";
import MempoolPanel from "../components/MempoolPanel";
import NetworkActivityPanel from "../components/NetworkActivityPanel";
import OnchainVolumePanel from "../components/OnchainVolumePanel";
import OrderFlowPanel from "../components/OrderFlowPanel";
import PriceChart from "../components/PriceChart";
import PriceHero from "../components/PriceHero";
import SmartMoneyLeaderboard from "../components/SmartMoneyLeaderboard";
import StablecoinSupplyPanel from "../components/StablecoinSupplyPanel";
import StakingFlowsPanel from "../components/StakingFlowsPanel";
import VolumeStructurePanel from "../components/VolumeStructurePanel";
import WhaleTransfersPanel from "../components/WhaleTransfersPanel";

export type PageId = "overview" | "markets" | "onchain" | "mempool";

export type PanelWidth = 1 | 2 | 3 | 4;

export type PanelDef = {
  /** Stable kebab-case id; persisted to LocalStorage and used as drag id. */
  id: string;
  /** Display name in the customize popover and topbar nav. */
  label: string;
  /** The panel component. May accept zero props or panel-specific props. */
  component: ComponentType<any>;
  /** Page this panel belongs to when not on overview. */
  defaultPage: PageId;
  /** Default column span on the bento grid (1=S, 2=M, 3=L, 4=Full). */
  defaultWidth: PanelWidth;
  /** True for panels that only make sense on overview (PriceHero). */
  homeOnly?: boolean;
};

export const PANELS: PanelDef[] = [
  { id: "price-hero", label: "Price", component: PriceHero, defaultPage: "overview", defaultWidth: 4, homeOnly: true },
  { id: "price-chart", label: "Chart", component: PriceChart, defaultPage: "markets", defaultWidth: 3 },
  { id: "derivatives", label: "Derivatives", component: DerivativesPanel, defaultPage: "markets", defaultWidth: 2 },
  { id: "smart-money", label: "Smart money", component: SmartMoneyLeaderboard, defaultPage: "markets", defaultWidth: 2 },
  { id: "order-flow", label: "Order flow", component: OrderFlowPanel, defaultPage: "markets", defaultWidth: 2 },
  { id: "volume-structure", label: "Volume structure", component: VolumeStructurePanel, defaultPage: "markets", defaultWidth: 2 },
  { id: "exchange-flows", label: "Exchange flows", component: ExchangeFlowsPanel, defaultPage: "onchain", defaultWidth: 1 },
  { id: "stablecoin-supply", label: "Stablecoin supply", component: StablecoinSupplyPanel, defaultPage: "onchain", defaultWidth: 1 },
  { id: "staking-flows", label: "Beacon flows", component: StakingFlowsPanel, defaultPage: "onchain", defaultWidth: 1 },
  { id: "lst-market-share", label: "LST market share", component: LstMarketSharePanel, defaultPage: "onchain", defaultWidth: 2 },
  { id: "onchain-volume", label: "On-chain volume", component: OnchainVolumePanel, defaultPage: "onchain", defaultWidth: 2 },
  { id: "network-activity", label: "Network activity", component: NetworkActivityPanel, defaultPage: "onchain", defaultWidth: 2 },
  { id: "whale-transfers", label: "Whale transfers", component: WhaleTransfersPanel, defaultPage: "onchain", defaultWidth: 2 },
  { id: "mempool", label: "Mempool", component: MempoolPanel, defaultPage: "mempool", defaultWidth: 2 },
  { id: "alerts", label: "Alerts", component: AlertEventsPanel, defaultPage: "mempool", defaultWidth: 2 },
];

export const PANELS_BY_ID: Record<string, PanelDef> = Object.fromEntries(
  PANELS.map((p) => [p.id, p]),
);

/** Default Overview layout. v2 shape: each entry carries an explicit width. */
export const DEFAULT_OVERVIEW_LAYOUT: { id: string; width: PanelWidth }[] = [
  { id: "price-hero", width: 4 },
  { id: "price-chart", width: 3 },
  { id: "exchange-flows", width: 1 },
  { id: "whale-transfers", width: 2 },
  { id: "smart-money", width: 2 },
];

/**
 * Static map of width → Tailwind class string used by `<SortablePanel>`.
 * Literal strings ensure Tailwind's PurgeCSS sees them at build time.
 *
 * The "responsive collapse" mapping intentionally lets a width-4 panel
 * span the whole row at every breakpoint (always full), and a width-1
 * panel widen at narrower viewports so it doesn't render absurdly small.
 */
export const SPAN_CLASS: Record<PanelWidth, string> = {
  1: "col-span-1",
  2: "col-span-1 md:col-span-2",
  3: "col-span-1 md:col-span-2 lg:col-span-3",
  4: "col-span-1 md:col-span-2 lg:col-span-3 xl:col-span-4",
};
