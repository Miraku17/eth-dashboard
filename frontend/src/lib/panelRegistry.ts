import type { ComponentType } from "react";

import AlertEventsPanel from "../components/AlertEventsPanel";
import BridgeFlowsPanel from "../components/BridgeFlowsPanel";
import CategoryNetFlowPanel from "../components/CategoryNetFlowPanel";
import CexNetFlowPanel from "../components/CexNetFlowPanel";
import DefiTvlPanel from "../components/DefiTvlPanel";
import DexPoolTvlPanel from "../components/DexPoolTvlPanel";
import DerivativesPanel from "../components/DerivativesPanel";
import ExchangeFlowsPanel from "../components/ExchangeFlowsPanel";
import LiquidationsPanel from "../components/LiquidationsPanel";
import LiveVolumePanel from "../components/LiveVolumePanel";
import LrtTvlPanel from "../components/LrtTvlPanel";
import LstMarketSharePanel from "../components/LstMarketSharePanel";
import MarketRegimePanel from "../components/MarketRegimePanel";
import MempoolPanel from "../components/MempoolPanel";
import NetworkActivityPanel from "../components/NetworkActivityPanel";
import OnchainPerpsPanel from "../components/OnchainPerpsPanel";
import OnchainVolumePanel from "../components/OnchainVolumePanel";
import OrderFlowPanel from "../components/OrderFlowPanel";
import PriceChart from "../components/PriceChart";
import PriceHero from "../components/PriceHero";
import SmartMoneyDirectionPanel from "../components/SmartMoneyDirectionPanel";
import SmartMoneyLeaderboard from "../components/SmartMoneyLeaderboard";
import StablecoinSupplyPanel from "../components/StablecoinSupplyPanel";
import StakingFlowsPanel from "../components/StakingFlowsPanel";
import VolumeStructurePanel from "../components/VolumeStructurePanel";
import WhaleTransfersPanel from "../components/WhaleTransfersPanel";

export type PageId = "overview" | "markets" | "onchain" | "mempool";

export type PanelWidth = 1 | 2 | 3 | 4;

/**
 * Sub-section within the Onchain page. Pages with too many panels (Onchain
 * now has 10+) get visual H2 dividers between sections so the eye can
 * scan. `OnchainPage` iterates ONCHAIN_SECTIONS in order and groups
 * panels by their `section` field.
 */
export type OnchainSection = "stablecoins" | "staking" | "defi" | "bridges" | "network";

export const ONCHAIN_SECTIONS: { id: OnchainSection; label: string }[] = [
  { id: "stablecoins", label: "Stablecoins" },
  { id: "staking", label: "Staking" },
  { id: "defi", label: "DeFi" },
  { id: "bridges", label: "Bridges (L1↔L2)" },
  { id: "network", label: "Network" },
];

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
  /** Sub-section within the Onchain page. Ignored on other pages. */
  section?: OnchainSection;
};

export const PANELS: PanelDef[] = [
  { id: "price-hero", label: "Price", component: PriceHero, defaultPage: "overview", defaultWidth: 4, homeOnly: true },
  { id: "market-regime", label: "Market regime", component: MarketRegimePanel, defaultPage: "overview", defaultWidth: 2 },
  { id: "smart-money-direction", label: "Smart-money direction", component: SmartMoneyDirectionPanel, defaultPage: "overview", defaultWidth: 2 },
  { id: "cex-net-flow", label: "CEX net flow", component: CexNetFlowPanel, defaultPage: "overview", defaultWidth: 2 },
  { id: "category-net-flow", label: "DeFi flows", component: CategoryNetFlowPanel, defaultPage: "overview", defaultWidth: 2 },
  { id: "price-chart", label: "Chart", component: PriceChart, defaultPage: "markets", defaultWidth: 3 },
  { id: "derivatives", label: "Derivatives", component: DerivativesPanel, defaultPage: "markets", defaultWidth: 2 },
  { id: "liquidations", label: "Liquidations", component: LiquidationsPanel, defaultPage: "markets", defaultWidth: 2 },
  { id: "smart-money", label: "Smart money", component: SmartMoneyLeaderboard, defaultPage: "markets", defaultWidth: 2 },
  { id: "order-flow", label: "Order flow", component: OrderFlowPanel, defaultPage: "markets", defaultWidth: 2 },
  { id: "volume-structure", label: "Volume structure", component: VolumeStructurePanel, defaultPage: "markets", defaultWidth: 2 },
  { id: "onchain-perps", label: "On-chain perps", component: OnchainPerpsPanel, defaultPage: "markets", defaultWidth: 3 },
  { id: "stablecoin-supply", label: "Stablecoin supply", component: StablecoinSupplyPanel, defaultPage: "onchain", defaultWidth: 1, section: "stablecoins" },
  { id: "live-volume", label: "Live volume", component: LiveVolumePanel, defaultPage: "onchain", defaultWidth: 2, section: "stablecoins" },
  { id: "whale-transfers", label: "Whale transfers", component: WhaleTransfersPanel, defaultPage: "onchain", defaultWidth: 2, section: "stablecoins" },
  { id: "exchange-flows", label: "Exchange flows", component: ExchangeFlowsPanel, defaultPage: "onchain", defaultWidth: 1, section: "stablecoins" },
  { id: "staking-flows", label: "Beacon flows", component: StakingFlowsPanel, defaultPage: "onchain", defaultWidth: 1, section: "staking" },
  { id: "lst-market-share", label: "LST market share", component: LstMarketSharePanel, defaultPage: "onchain", defaultWidth: 2, section: "staking" },
  { id: "lrt-tvl", label: "LRT issuers", component: LrtTvlPanel, defaultPage: "onchain", defaultWidth: 2, section: "staking" },
  { id: "defi-tvl", label: "DeFi TVL", component: DefiTvlPanel, defaultPage: "onchain", defaultWidth: 2, section: "defi" },
  { id: "dex-pool-tvl", label: "DEX pool TVL", component: DexPoolTvlPanel, defaultPage: "onchain", defaultWidth: 2, section: "defi" },
  { id: "bridge-flows", label: "Bridge flows", component: BridgeFlowsPanel, defaultPage: "onchain", defaultWidth: 2, section: "bridges" },
  { id: "onchain-volume", label: "On-chain volume", component: OnchainVolumePanel, defaultPage: "onchain", defaultWidth: 2, section: "network" },
  { id: "network-activity", label: "Network activity", component: NetworkActivityPanel, defaultPage: "onchain", defaultWidth: 2, section: "network" },
  { id: "mempool", label: "Mempool", component: MempoolPanel, defaultPage: "mempool", defaultWidth: 2 },
  { id: "alerts", label: "Alerts", component: AlertEventsPanel, defaultPage: "mempool", defaultWidth: 2 },
];

export const PANELS_BY_ID: Record<string, PanelDef> = Object.fromEntries(
  PANELS.map((p) => [p.id, p]),
);

/** Default Overview layout. v2 shape: each entry carries an explicit width. */
export const DEFAULT_OVERVIEW_LAYOUT: { id: string; width: PanelWidth }[] = [
  { id: "price-hero", width: 4 },
  { id: "market-regime", width: 2 },
  { id: "smart-money-direction", width: 2 },
  { id: "cex-net-flow", width: 2 },
  { id: "category-net-flow", width: 2 },
  { id: "price-chart", width: 2 },
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
