/**
 * Source of truth for translation keys. The type
 * `keyof typeof en` is what other layers consume to ensure type-safe
 * key lookup. Task 3 fills this out with the full ~250-key inventory.
 */
export const en = {
  // ---------------------------------------------------------------------------
  // Navigation
  // ---------------------------------------------------------------------------
  "nav.overview": "Overview",
  "nav.markets": "Markets",
  "nav.onchain": "Onchain",
  "nav.mempool": "Mempool",

  // ---------------------------------------------------------------------------
  // Common UI
  // ---------------------------------------------------------------------------
  "common.loading": "loading…",
  "common.unavailable": "unavailable",
  "common.no_data_yet": "no data yet",
  "common.save": "Save",
  "common.cancel": "Cancel",
  "common.close": "Close",
  "common.edit": "Edit",
  "common.delete": "Delete",
  "common.clear": "clear",
  "common.positions": "positions",
  "common.all": "All",
  "common.full": "Full",

  // Indicator picker (PriceChart)
  "indicators.label": "Indicators",
  "indicators.ma": "MA (20 / 50 / 200)",
  "indicators.ema": "EMA (12 / 26)",
  "indicators.bb": "Bollinger Bands",
  "indicators.rsi": "RSI (14)",
  "indicators.macd": "MACD (12, 26, 9)",

  // DEX pool filter (DexPoolTvlPanel)
  "dex_pool.all_dexes": "All DEXes",

  // Volume structure mode toggle (VolumeStructurePanel)
  "volume_structure.pct_share": "% share",

  // Sortable panel resize tooltips (SortablePanel)
  "panel_size.resize_to": "Resize to {{label}}",

  // LiveVolume MA-overlay extras (added post-merge with the MA overlay PR)
  "live-volume.aria.time_window": "Time window",
  "live-volume.data_age_latest": "latest",
  "live-volume.tooltip.ma_period": "{{period}}m MA",
  "live-volume.legend.trend": "trend",
  "live-volume.legend.baseline": "baseline",
  "live-volume.warming_up": "warming up — {{period}}m baseline in {{remaining}}m",
  "live-volume.trend_vs_avg": "{{sign}}{{pct}}% vs {{period}}m avg {{arrow}}",

  // ---------------------------------------------------------------------------
  // Topbar / DashboardShell
  // ---------------------------------------------------------------------------
  "topbar.systems_nominal": "Systems nominal",
  "topbar.degraded": "Degraded",
  "topbar.data_freshness": "Data freshness",
  "topbar.customize": "Customize",
  "topbar.done": "Done",
  "topbar.reset": "Reset",
  "topbar.logout": "Logout",
  "topbar.signed_in_as": "Signed in as",
  "topbar.footer": "Data: Binance · Dune Analytics · Alchemy · Etherscan · CoinGecko",

  // ---------------------------------------------------------------------------
  // Reset overview modal (Topbar)
  // ---------------------------------------------------------------------------
  "reset_overview.title": "Reset overview",
  "reset_overview.body": "This will restore the default panel selection, order, and sizes for your overview.",
  "reset_overview.detail": "Any panels you've added or removed and any size changes will be discarded. This action can't be undone.",
  "reset_overview.confirm": "Reset layout",

  // ---------------------------------------------------------------------------
  // Overview page
  // ---------------------------------------------------------------------------
  "overview.empty": "Click {{customize}} to add panels to your overview.",

  // ---------------------------------------------------------------------------
  // Auth / Login
  // ---------------------------------------------------------------------------
  "login.title": "Etherscope",
  "login.tagline": "Sign in to continue",
  "login.username": "Username",
  "login.password": "Password",
  "login.submit": "Sign in",
  "login.submitting": "Signing in…",
  "login.remember": "Keep me signed in for 90 days",
  "auth.loading": "Loading…",

  // ---------------------------------------------------------------------------
  // Alerts panel (AlertEventsPanel)
  // ---------------------------------------------------------------------------
  "alerts.title": "Alerts",
  "alerts.subtitle_with_rules": "{{active}}/{{total}} rules active · fires in last 24h",
  "alerts.subtitle_no_rules": "rules · fires in last 24h",
  "alerts.tab.events": "Events",
  "alerts.tab.rules": "Rules",
  "alerts.new_rule": "+ New rule",
  "alerts.empty": "no alerts in the last 24h",
  "alerts.empty_no_rules": "no alerts in the last 24h — no rules configured yet",
  "alerts.col.fired": "Fired",
  "alerts.col.rule": "Rule",
  "alerts.col.type": "Type",
  "alerts.col.detail": "Detail",
  "alerts.col.delivery": "Delivery",
  "alerts.modal.new": "New alert rule",
  "alerts.modal.edit": "Edit rule · {{name}}",
  "alerts.toast.created": "Rule created",
  "alerts.toast.updated": "Rule updated",

  // ---------------------------------------------------------------------------
  // Alert RuleForm
  // ---------------------------------------------------------------------------
  "rule_form.label.name": "Name",
  "rule_form.label.rule_type": "Rule type",
  "rule_form.label.symbol": "Symbol",
  "rule_form.label.threshold_usd": "Threshold (USD)",
  "rule_form.label.window_minutes": "Window (minutes)",
  "rule_form.label.trigger_pct": "Trigger % (negative = down move)",
  "rule_form.label.asset": "Asset",
  "rule_form.label.min_usd": "Minimum USD",
  "rule_form.label.direction": "Direction",
  "rule_form.label.exchange": "Exchange",
  "rule_form.label.window_hours": "Window (hours)",
  "rule_form.label.min_score": "Minimum smart score (USD)",
  "rule_form.label.cooldown": "Cooldown (minutes, optional)",
  "rule_form.label.channels": "Channels",
  "rule_form.placeholder.name": "e.g. ETH above $4k",
  "rule_form.placeholder.cooldown": "default: 15 (price + netflow only)",
  "rule_form.rule_type_locked": "rule type can't be changed after creation",
  "rule_form.dir.any_exchange": "any (either side labeled)",
  "rule_form.dir.to_exchange": "to exchange",
  "rule_form.dir.from_exchange": "from exchange",
  "rule_form.dir.net": "|net|",
  "rule_form.dir.inflow": "inflow",
  "rule_form.dir.outflow": "outflow",
  "rule_form.dir.any_smart": "any (smart on either side)",
  "rule_form.dir.from_smart": "smart sender (smart →)",
  "rule_form.dir.to_smart": "smart receiver (→ smart)",
  "rule_form.channel.telegram": "Telegram",
  "rule_form.channel.webhook": "Webhook",
  "rule_form.no_channels": "No channels — events will still be logged in the dashboard.",
  "rule_form.submit.create": "Create rule",
  "rule_form.submit.save": "Save changes",
  "rule_form.submit.saving": "Saving…",
  "rule_form.error.name_required": "name is required",
  "rule_form.error.webhook_url_required": "webhook URL is required when webhook channel is enabled",
  "rule_form.error.cooldown_invalid": "cooldown must be a non-negative number",
  "rule_form.error.save_failed": "failed to save",

  // ---------------------------------------------------------------------------
  // Alert RulesList
  // ---------------------------------------------------------------------------
  "rules_list.empty": "No rules yet — click {{new_rule}} to create one.",
  "rules_list.col.name": "Name",
  "rules_list.col.type": "Type",
  "rules_list.col.condition": "Condition",
  "rules_list.col.channels": "Channels",
  "rules_list.col.cooldown": "Cooldown",
  "rules_list.col.enabled": "Enabled",
  "rules_list.col.actions": "Actions",
  "rules_list.aria.enable": "Enable",
  "rules_list.aria.disable": "Disable",
  "rules_list.confirm_delete": "Delete rule \"{{name}}\"?",
  "rules_list.cooldown_default": "default",

  // ---------------------------------------------------------------------------
  // Wallet drawer (WalletDrawer)
  // ---------------------------------------------------------------------------
  "wallet.drawer.heading": "Wallet",
  "wallet.etherscan_link": "Etherscan ↗",
  "wallet.aria.close": "Close",
  "wallet.unavailable": "unavailable — try again",
  "wallet.section.address": "Address",
  "wallet.section.current_balance": "Current balance",
  "wallet.balance_history_unavailable": "Balance history unavailable — RPC endpoint not configured.",
  "wallet.section.active_since": "Active since",
  "wallet.section.last_seen": "Last seen",
  "wallet.section.tx_count": "Tx count",
  "wallet.section.token_holdings": "Token holdings",
  "wallet.token_holdings.subtitle": "· top {{count}} by USD",
  "wallet.section.net_flow": "Net flow · 7d (whale moves)",
  "wallet.section.top_counterparties": "Top counterparties · 30d",
  "wallet.counterparties.empty": "No whale-sized counterparties in the last 30 days.",
  "wallet.section.recent_activity": "Recent whale activity",
  "wallet.recent_activity.empty": "No transfers above the whale threshold involving this address. The wallet may still be active in smaller moves.",
  "wallet.section.linked_wallets": "Linked wallets ({{count}})",
  "wallet.below_threshold": "This wallet is below the whale-tracking threshold (≥100 ETH or ≥$250k stables per transfer). Profile shows on-chain balance only — smaller moves are not indexed.",
  "wallet.netflow.no_moves": "no whale moves in 7d",
  "wallet.netflow.active_days": "{{count}} of 7 days active",
  "wallet.score.title": "Wallet score · 30d",
  "wallet.score.realized_pnl": "Realized PnL",
  "wallet.score.win_rate": "Win rate",
  "wallet.score.volume": "Volume",
  "wallet.score.updated": "updated {{age}}",
  "wallet.score.swaps": "{{count}} swaps · v1 score = realized PnL",
  "wallet.score.smart_badge_title": "Smart-money tier {{tier}}",
  "wallet.token.unpriced": "unpriced",
  "wallet.transfer.open_tx": "open tx on Etherscan",

  // ---------------------------------------------------------------------------
  // Whale transfers panel (WhaleTransfersPanel)
  // ---------------------------------------------------------------------------
  "whale-transfers.title": "Whale transfers",
  "whale-transfers.subtitle": "{{count}} moves · {{total}} total · last {{hours}}h",
  "whale-transfers.subtitle_with_smart": "{{count}} moves · {{total}} total · last {{hours}}h · {{smart}} smart-money",
  "whale-transfers.subtitle_default": "ETH ≥ 500 · Stables ≥ $1M",
  "whale-transfers.smart_only": "★ Smart only",
  "whale-transfers.smart_only_title": "Show only transfers involving wallets with ≥ $100k 30d realized PnL",
  "whale-transfers.aria.asset_filter": "Filter by asset",
  "whale-transfers.filter.clear": "clear",
  "whale-transfers.pending_label": "Pending ({{count}})",
  "whale-transfers.empty_smart": "no smart-money moves in the last {{hours}}h — toggle ★ off to see all whales",
  "whale-transfers.empty": "no whale transfers yet — listener needs ALCHEMY_API_KEY and a few blocks",
  "whale-transfers.col.time": "Time",
  "whale-transfers.col.asset": "Asset",
  "whale-transfers.col.from": "From",
  "whale-transfers.col.to": "To",
  "whale-transfers.col.amount": "Amount",
  "whale-transfers.col.usd": "USD",
  "whale-transfers.col.tx": "Tx",
  "whale-transfers.open_etherscan": "Open in Etherscan",

  // ---------------------------------------------------------------------------
  // Flow kind badge labels (WhaleTransfersPanel row badges)
  // ---------------------------------------------------------------------------
  "flow.to_cex": "→ CEX",
  "flow.from_cex": "← CEX",
  "flow.to_dex": "→ DEX",
  "flow.from_dex": "← DEX",
  "flow.to_lending": "→ Lending",
  "flow.from_lending": "← Lending",
  "flow.to_staking": "→ Staking",
  "flow.from_staking": "← Staking",
  "flow.to_l2": "→ L2",
  "flow.from_l2": "← L2",
  "flow.to_hl": "→ HL",
  "flow.from_hl": "← HL",

  // ---------------------------------------------------------------------------
  // Flow filter chip labels (WhaleTransfersPanel chips)
  // ---------------------------------------------------------------------------
  "flow_chip.cex_in": "→ Exchange",
  "flow_chip.cex_out": "← Exchange",
  "flow_chip.dex": "DEX",
  "flow_chip.lending": "Lending",
  "flow_chip.staking": "Staking",
  "flow_chip.bridge": "Bridge",
  "flow_chip.hyperliquid": "Hyperliquid",
  "flow_chip.wallet": "Wallet ↔ Wallet",

  // ---------------------------------------------------------------------------
  // Mempool panel (MempoolPanel)
  // ---------------------------------------------------------------------------
  "mempool.title": "Mempool whales",
  "mempool.subtitle": "{{count}} pending · {{total}} unconfirmed · {{gas}} gwei median",
  "mempool.subtitle_empty": "live whale-sized pending transactions from the local node",
  "mempool.subtitle_no_gas": "{{count}} pending · {{total}} unconfirmed",
  "mempool.empty": "no pending whales right now — needs a self-hosted node (ALCHEMY_WS_URL); whales appear within seconds when broadcast",
  "mempool.col.age": "Age",
  "mempool.col.asset": "Asset",
  "mempool.col.from": "From",
  "mempool.col.to": "To",
  "mempool.col.amount": "Amount",
  "mempool.col.usd": "USD",
  "mempool.col.gas": "Gas",
  "mempool.col.tx": "Tx",

  // ---------------------------------------------------------------------------
  // Network activity panel (NetworkActivityPanel)
  // ---------------------------------------------------------------------------
  "network-activity.title": "Network activity",
  "network-activity.subtitle_live": "last block {{time}}",
  "network-activity.subtitle_empty": "per-block stats · needs ALCHEMY_API_KEY",
  "network-activity.stat.gas_price": "Gas price",
  "network-activity.stat.base_fee": "Base fee",
  "network-activity.stat.block_time": "Block time",
  "network-activity.stat.tx_per_block": "Tx / block",
  "network-activity.empty": "no network data yet — realtime listener must be running with a valid ALCHEMY_API_KEY",
  "network-activity.chart.gas": "Gas (gwei)",
  "network-activity.chart.tx": "Transactions per block",

  // ---------------------------------------------------------------------------
  // Price hero (PriceHero)
  // ---------------------------------------------------------------------------
  "price-hero.mainnet": "· Mainnet",
  "price-hero.24h_high": "24h High",
  "price-hero.24h_low": "24h Low",
  "price-hero.24h_volume": "24h Volume",
  "price-hero.24h_change": "24h Change",
  "price-hero.range.low": "Low",
  "price-hero.range.high": "High",

  // ---------------------------------------------------------------------------
  // Price chart (PriceChart)
  // ---------------------------------------------------------------------------
  "price-chart.title": "ETH / USDT",
  "price-chart.subtitle_loading": "loading…",
  "price-chart.subtitle_error": "chart unavailable",
  "price-chart.subtitle_disconnected": "{{count}} {{tf}} candles · live disconnected — retrying",
  "price-chart.subtitle_live": "{{count}} {{tf}} candles · Binance live",
  "price-chart.zoom_in": "Zoom in",
  "price-chart.zoom_out": "Zoom out",

  // ---------------------------------------------------------------------------
  // Stablecoin flow curve (StableFlowCurvePanel)
  // ---------------------------------------------------------------------------
  "stable-flow-curve.title": "Stablecoin volume curve",
  "stable-flow-curve.subtitle": "Per-asset on-chain transfer volume · {{bucket}} buckets",
  "stable-flow-curve.empty": "no volume data in this window yet",
  "stable-flow-curve.tile.total_volume": "Total volume",
  "stable-flow-curve.tile.window": "Window ({{bucket}})",
  "stable-flow-curve.tile.vs_ma": "vs MA{{period}}",
  "stable-flow-curve.tile.vs_ma_hint": "Latest bucket vs trailing avg",
  "stable-flow-curve.legend.ma_fast": "MA{{period}} (fast)",
  "stable-flow-curve.legend.ma_slow": "MA{{period}} (slow)",
  "stable-flow-curve.chart_heading": "Transfer volume",

  // ---------------------------------------------------------------------------
  // Stablecoin marketcap (StablecoinMarketcapPanel)
  // ---------------------------------------------------------------------------
  "stable-marketcap.title": "Stablecoin marketcap",
  "stable-marketcap.subtitle": "Per-asset circulating supply curve · {{bucket}} buckets",
  "stable-marketcap.empty": "no supply data yet — first cron tick lands within ~60s",
  "stable-marketcap.tile.total_cap": "Total cap",
  "stable-marketcap.tile.latest": "Latest bucket",
  "stable-marketcap.tile.delta_window": "Δ window ({{bucket}})",
  "stable-marketcap.tile.delta_hint": "Last bucket vs first",

  // ---------------------------------------------------------------------------
  // Shared curve panel (CurvePanelShell + per-flow panels)
  // ---------------------------------------------------------------------------
  "curve.legend.ma_fast": "MA{{period}} (fast)",
  "curve.legend.ma_slow": "MA{{period}} (slow)",
  "flow-curve.line.inflow": "Inflow",
  "flow-curve.line.outflow": "Outflow",
  "flow-curve.line.net": "Net",
  "flow-curve.tile.inflow": "Total inflow",
  "flow-curve.tile.outflow": "Total outflow",
  "flow-curve.tile.net_last": "Net (last bucket)",
  "flow-curve.tile.net_hint": "Inflow − outflow",
  "flow-curve.tile.window": "Window ({{bucket}})",
  "flow-curve.tile.vs_ma": "vs MA{{period}}",
  "flow-curve.tile.vs_ma_hint": "Latest vs trailing avg",

  // CEX flow curve
  "cex-flow-curve.title": "CEX flow curve",
  "cex-flow-curve.subtitle": "Whale flows in/out of CEX hot wallets · {{bucket}} buckets",
  "cex-flow-curve.empty": "no labeled CEX flows in this window",

  // DEX flow curve
  "dex-flow-curve.title": "DEX flow curve",
  "dex-flow-curve.subtitle": "Whale flows in/out of DEX routers + pools · {{bucket}} buckets",
  "dex-flow-curve.empty": "no labeled DEX flows in this window",
  "dex-flow-curve.line.sell": "Selling (wallet → DEX)",
  "dex-flow-curve.line.buy": "Buying (DEX → wallet)",
  "dex-flow-curve.tile.sell": "Selling volume",
  "dex-flow-curve.tile.buy": "Buying volume",
  "dex-flow-curve.tile.net_hint": "Sell − buy",

  // DeFi TVL curve
  "defi-tvl-curve.title": "DeFi TVL curve",
  "defi-tvl-curve.subtitle": "Per-protocol TVL · {{bucket}} buckets",
  "defi-tvl-curve.empty": "no TVL data in this window",
  "defi-tvl-curve.tile.total": "Total TVL",
  "defi-tvl-curve.tile.latest": "Latest bucket",
  "defi-tvl-curve.tile.delta": "Δ window ({{bucket}})",
  "defi-tvl-curve.tile.delta_hint": "Last bucket vs first",

  // ---------------------------------------------------------------------------
  // Derivatives panel (DerivativesPanel)
  // ---------------------------------------------------------------------------
  "derivatives.title": "Derivatives",
  "derivatives.subtitle": "OI + funding rates · ETH perp · Binance / Bybit / OKX / Deribit",
  "derivatives.empty": "no derivatives data yet — worker runs once/hour. First sync happens at worker startup; check back in ~60s.",
  "derivatives.chart.funding": "Funding rate",
  "derivatives.chart.oi": "Open interest (USD)",
  "derivatives.pill.funding": "Funding",
  "derivatives.pill.oi": "OI",

  // ---------------------------------------------------------------------------
  // Liquidations panel (LiquidationsPanel)
  // ---------------------------------------------------------------------------
  "liquidations.title": "Liquidations",
  "liquidations.subtitle": "Perp futures · ETH-USD · {{venue}}",
  "liquidations.tile.longs": "Longs liquidated",
  "liquidations.tile.shorts": "Shorts liquidated",
  "liquidations.tile.skew": "Skew · largest",
  "liquidations.skew_pct": "{{pct}}% long",
  "liquidations.largest": "largest {{value}}",
  "liquidations.positions_count": "{{count}} positions",
  "liquidations.empty": "no liquidations in the last {{range}} — quiet market window. Listener subscribes to Bybit's allLiquidation.ETHUSDT; events stream as they happen.",

  // ---------------------------------------------------------------------------
  // On-chain perps panel (OnchainPerpsPanel)
  // ---------------------------------------------------------------------------
  "onchain-perps.title": "On-chain perps",
  "onchain-perps.subtitle": "GMX V2 · Arbitrum",
  "onchain-perps.tab.events": "Events",
  "onchain-perps.tab.liquidations": "Liquidations",
  "onchain-perps.tab.positions": "Open positions",
  "onchain-perps.filter.kind": "Kind",
  "onchain-perps.filter.min_size": "Min size",
  "onchain-perps.filter.any": "any",
  "onchain-perps.events.empty": "no events in the last 24h matching this filter — Arbitrum listener may still be warming up if the deploy is recent.",
  "onchain-perps.liq.empty": "no liquidations in 24h.",
  "onchain-perps.positions.empty": "no open positions yet.",
  "onchain-perps.tile.longs_liq": "Longs liquidated",
  "onchain-perps.tile.shorts_liq": "Shorts liquidated",
  "onchain-perps.tile.open_skew": "Open skew",
  "onchain-perps.tile.events_sub": "{{count}} events 24h",
  "onchain-perps.tile.biggest_sub": "biggest {{value}}",
  "onchain-perps.col.when": "When",
  "onchain-perps.col.account": "Account",
  "onchain-perps.col.market": "Market",
  "onchain-perps.col.kind": "Kind",
  "onchain-perps.col.side": "Side",
  "onchain-perps.col.size": "Size",
  "onchain-perps.col.lev": "Lev",
  "onchain-perps.col.price": "Price",
  "onchain-perps.col.pnl": "PnL",
  "onchain-perps.col.opened": "Opened",

  // ---------------------------------------------------------------------------
  // Smart money direction panel (SmartMoneyDirectionPanel)
  // ---------------------------------------------------------------------------
  "smart-money-direction.title": "Smart-money direction",
  "smart-money-direction.subtitle": "Last 24h · 30d realized PnL ≥ {{min}}",
  "smart-money-direction.empty": "no smart-money DEX swaps in the last 24h — the daily score_wallets cron produces this set; if it hasn't run yet, the panel will populate on its first pass.",
  "smart-money-direction.verdict.buying": "Net buying",
  "smart-money-direction.verdict.selling": "Net selling",
  "smart-money-direction.verdict.balanced": "Balanced",
  "smart-money-direction.wallets_active": "{{count}} smart wallet active",
  "smart-money-direction.wallets_active_plural": "{{count}} smart wallets active",
  "smart-money-direction.tile.bought": "Bought",
  "smart-money-direction.tile.sold": "Sold",
  "smart-money-direction.net_7d": "Net · 7d",

  // ---------------------------------------------------------------------------
  // Smart money leaderboard (SmartMoneyLeaderboard)
  // ---------------------------------------------------------------------------
  "smart-money.title": "Smart money leaderboard",
  "smart-money.subtitle": "Top 50 ETH DEX traders by 30d realized PnL · WETH only · mainnet",
  "smart-money.empty": "no snapshot yet — refresh runs daily at 03:00 UTC. Needs DUNE_QUERY_ID_SMART_MONEY_LEADERBOARD set.",
  "smart-money.stale": "Snapshot is older than {{hours}}h — daily refresh may have stalled.",
  "smart-money.col.rank": "#",
  "smart-money.col.wallet": "Wallet",
  "smart-money.col.realized_pnl": "Realized PnL",
  "smart-money.col.unrealized": "Unrealized",
  "smart-money.col.win_rate": "Win rate",
  "smart-money.col.trades": "Trades",
  "smart-money.col.volume": "Volume",

  // ---------------------------------------------------------------------------
  // Market regime panel (MarketRegimePanel)
  // ---------------------------------------------------------------------------
  "market-regime.title": "Market regime",
  "market-regime.subtitle": "Rule-based · 6-feature score · refreshes hourly",
  "market-regime.score_confidence": "score · confidence",
  "market-regime.hint.euphoria": "extreme bearish — leverage stretched",
  "market-regime.hint.distribution": "mild bearish bias",
  "market-regime.hint.neutral": "no strong directional bias",
  "market-regime.hint.accumulation": "mild bullish bias",
  "market-regime.hint.capitulation": "extreme bullish — fear flush",

  // ---------------------------------------------------------------------------
  // CEX net flow panel (CexNetFlowPanel)
  // ---------------------------------------------------------------------------
  "cex-net-flow.title": "CEX net flow",
  "cex-net-flow.subtitle": "Live · whale ETH + stables in/out of exchanges",
  "cex-net-flow.empty": "no CEX-classified whale transfers yet — listener will populate as new whale moves to/from exchange hot wallets land.",
  "cex-net-flow.verdict.balanced": "balanced",
  "cex-net-flow.verdict.inflow": "net inflow",
  "cex-net-flow.verdict.outflow": "net outflow",
  "cex-net-flow.largest_inflow": "Biggest single inflow",
  "cex-net-flow.largest_outflow": "Biggest single outflow",

  // ---------------------------------------------------------------------------
  // Category net flow panel (CategoryNetFlowPanel)
  // ---------------------------------------------------------------------------
  "category-net-flow.title": "DeFi flows",
  "category-net-flow.subtitle": "Live · whale moves into / out of DEX, lending, staking, bridges",
  "category-net-flow.empty": "no classified transfers yet — listener will populate as whale moves to/from DeFi contracts land.",
  "category-net-flow.moves_singular": "{{count}} move",
  "category-net-flow.moves_plural": "{{count}} moves",

  // ---------------------------------------------------------------------------
  // Exchange flows panel (ExchangeFlowsPanel)
  // ---------------------------------------------------------------------------
  "exchange-flows.title": "Exchange netflows",
  "exchange-flows.subtitle": "last {{range}} · Dune · labeled CEX wallets",
  "exchange-flows.empty": "no data yet — waiting for Dune sync",
  "exchange-flows.row.in": "in {{value}}",
  "exchange-flows.row.out": "out {{value}}",

  // ---------------------------------------------------------------------------
  // Order flow panel (OrderFlowPanel)
  // ---------------------------------------------------------------------------
  "order-flow.title": "Order flow",
  "order-flow.subtitle": "DEX buy vs sell pressure · ETH (WETH) · last {{range}}",
  "order-flow.empty": "no data yet — waiting for Dune order-flow sync (first run at worker startup, then every 8h). Needs DUNE_QUERY_ID_ORDER_FLOW set.",
  "order-flow.tile.buy": "Buy volume",
  "order-flow.tile.sell": "Sell volume",
  "order-flow.tile.net": "Net pressure",
  "order-flow.tile.trades": "{{count}} trades",
  "order-flow.by_dex": "By DEX · last {{range}}",

  // ---------------------------------------------------------------------------
  // Mantle order flow panel (MantleOrderFlowPanel)
  // ---------------------------------------------------------------------------
  "mantle-order-flow.title": "Mantle order flow (24h)",
  "mantle-order-flow.subtitle": "MNT buy / sell pressure on Agni",
  "mantle-order-flow.empty": "no data yet — set MANTLE_WS_URL and bring up the mantle docker compose profile.",
  "mantle-order-flow.tile.buy": "Buy volume",
  "mantle-order-flow.tile.sell": "Sell volume",
  "mantle-order-flow.tile.net": "Net pressure",
  "mantle-order-flow.price_unavailable": "USD pricing unavailable (CoinGecko); chart shows MNT-denominated bars when reachable.",

  // ---------------------------------------------------------------------------
  // Volume structure panel (VolumeStructurePanel)
  // ---------------------------------------------------------------------------
  "volume-structure.title": "Volume structure",
  "volume-structure.subtitle": "DEX volume by trade size · ETH (WETH) · last {{range}}",
  "volume-structure.empty": "no data yet — needs DUNE_QUERY_ID_VOLUME_BUCKETS set; first sync runs at worker startup, then every 8h",
  "volume-structure.tile.share": "{{pct}}% share",

  // ---------------------------------------------------------------------------
  // Stablecoin supply panel (StablecoinSupplyPanel)
  // ---------------------------------------------------------------------------
  "stablecoin-supply.title": "Stablecoin supply Δ",
  "stablecoin-supply.subtitle": "last {{range}} · mint vs burn",
  "stablecoin-supply.empty": "no data yet — waiting for Dune sync",
  "stablecoin-supply.row.mint_burn": "mint {{mint}} / burn {{burn}}",
  "stablecoin-supply.group_label": "{{peg}} stables",

  // ---------------------------------------------------------------------------
  // Live volume panel (LiveVolumePanel)
  // ---------------------------------------------------------------------------
  "live-volume.title": "Live on-chain volume",
  "live-volume.subtitle": "stables · per-minute · {{minutes}}m window · ~5s refresh",
  "live-volume.empty": "no data yet — realtime listener needs blocks to arrive",
  "live-volume.minutes_shown": "{{count}} minutes shown",
  "live-volume.window_total": "{{total}} window total",

  // ---------------------------------------------------------------------------
  // Onchain volume panel (OnchainVolumePanel)
  // ---------------------------------------------------------------------------
  "onchain-volume.title": "On-chain transfer volume",
  "onchain-volume.subtitle": "stacked daily USD · live · derived from realtime listener",
  "onchain-volume.empty": "no data yet — waiting for the realtime listener to populate.",

  // ---------------------------------------------------------------------------
  // Staking flows panel (StakingFlowsPanel)
  // ---------------------------------------------------------------------------
  "staking-flows.title": "Beacon flows",
  "staking-flows.subtitle": "last {{range}} · staking deposits vs validator exits",
  "staking-flows.empty": "no data yet — waiting for Dune sync",
  "staking-flows.total_staked": "Total ETH staked",
  "staking-flows.active_validators": "{{count}} active validators",
  "staking-flows.active_validators_dash": "active validators —",
  "staking-flows.leg.deposits": "Deposits",
  "staking-flows.leg.full_exits": "Full exits",
  "staking-flows.partial_withdrawals": "rewards skim (partial withdrawals):",
  "staking-flows.by_issuer": "By issuer ({{range}})",
  "staking-flows.col.deposits": "deposits",
  "staking-flows.col.exits": "exits",
  "staking-flows.col.net": "net",

  // ---------------------------------------------------------------------------
  // LST market share panel (LstMarketSharePanel)
  // ---------------------------------------------------------------------------
  "lst-market-share.title": "LST market share",
  "lst-market-share.subtitle": "last {{range}} · ETH-equivalent supply per token",
  "lst-market-share.empty": "no data yet — waiting for first hourly sync",
  "lst-market-share.apr_label": "APR",

  // ---------------------------------------------------------------------------
  // LRT TVL panel (LrtTvlPanel)
  // ---------------------------------------------------------------------------
  "lrt-tvl.title": "LRT issuers",
  "lrt-tvl.subtitle": "Liquid restaking · Ethereum mainnet · DefiLlama",
  "lrt-tvl.empty": "no data yet — first hourly sync pending",
  "lrt-tvl.total": "{{value}} total",

  // ---------------------------------------------------------------------------
  // DeFi TVL panel (DefiTvlPanel)
  // ---------------------------------------------------------------------------
  "defi-tvl.title": "DeFi TVL",
  "defi-tvl.subtitle": "Ethereum mainnet · per-protocol locked balances · DefiLlama",
  "defi-tvl.empty": "no data yet — first hourly sync pending",
  "defi-tvl.locked": "{{value}} locked",
  "defi-tvl.more_assets": "+ {{count}} more assets · {{value}} combined",
  "defi-tvl.aria.select_protocol": "Select DeFi protocol",

  // ---------------------------------------------------------------------------
  // DEX pool TVL panel (DexPoolTvlPanel)
  // ---------------------------------------------------------------------------
  "dex-pool-tvl.title": "DEX pool TVL",
  "dex-pool-tvl.subtitle": "Ethereum mainnet · top {{n}} pools by TVL · DefiLlama",
  "dex-pool-tvl.empty": "no data yet — first hourly sync pending",
  "dex-pool-tvl.pools_shown": "{{count}} pools shown",
  "dex-pool-tvl.combined": "{{value}} combined",
  "dex-pool-tvl.aria.filter": "Filter by DEX",

  // ---------------------------------------------------------------------------
  // Bridge flows panel (BridgeFlowsPanel)
  // ---------------------------------------------------------------------------
  "bridge-flows.title": "Bridge flows",
  "bridge-flows.subtitle": "L1 ↔ L2 · last {{range}} · Arbitrum / Base / Optimism / zkSync",
  "bridge-flows.empty": "no data yet — waiting for first Dune sync",
  "bridge-flows.deposit_withdraw": "deposit {{deposit}} / withdraw {{withdraw}}",
  "bridge-flows.net_l1_to_l2": "L1 → L2",
  "bridge-flows.net_l2_to_l1": "L2 → L1",

  // ---------------------------------------------------------------------------
  // Onchain page section headings
  // ---------------------------------------------------------------------------
  "section.stablecoins": "Stablecoins",
  "section.staking": "Staking",
  "section.defi": "DeFi",
  "section.bridges": "Bridges (L1↔L2)",
  "section.network": "Network",
  "section.other": "Other",
} as const;
