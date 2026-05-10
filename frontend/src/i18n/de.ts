/**
 * German translations. Type-checked against `en.ts` via
 * `Record<TranslationKey, string>` — TypeScript fails the build if any
 * key is missing or has a non-string value.
 *
 * Translation rules: see `docs/i18n-glossary.md`. Crypto jargon, asset
 * symbols, and DEX/CEX names stay English. Use formal German ("Sie")
 * for all user-facing prompts.
 */
import type { TranslationKey } from "./types";

export const de: Record<TranslationKey, string> = {
  // ---------------------------------------------------------------------------
  // Navigation
  // ---------------------------------------------------------------------------
  "nav.overview": "Übersicht",
  "nav.markets": "Märkte",
  "nav.onchain": "On-Chain",
  "nav.mempool": "Mempool",

  // ---------------------------------------------------------------------------
  // Common UI
  // ---------------------------------------------------------------------------
  "common.loading": "Laden…",
  "common.unavailable": "Nicht verfügbar",
  "common.no_data_yet": "Noch keine Daten",
  "common.save": "Speichern",
  "common.cancel": "Abbrechen",
  "common.close": "Schließen",
  "common.edit": "Bearbeiten",
  "common.delete": "Löschen",
  "common.clear": "Zurücksetzen",
  "common.positions": "Positionen",

  // ---------------------------------------------------------------------------
  // Topbar / DashboardShell
  // ---------------------------------------------------------------------------
  "topbar.systems_nominal": "Systeme normal",
  "topbar.degraded": "Eingeschränkt",
  "topbar.data_freshness": "Datenaktualität",
  "topbar.customize": "Anpassen",
  "topbar.done": "Fertig",
  "topbar.reset": "Zurücksetzen",
  "topbar.logout": "Abmelden",
  "topbar.signed_in_as": "Angemeldet als",
  "topbar.footer": "Daten: Binance · Dune Analytics · Alchemy · Etherscan · CoinGecko",

  // ---------------------------------------------------------------------------
  // Reset overview modal (Topbar)
  // ---------------------------------------------------------------------------
  "reset_overview.title": "Übersicht zurücksetzen",
  "reset_overview.body": "Die Standard-Panelauswahl, -reihenfolge und -größen der Übersicht werden wiederhergestellt.",
  "reset_overview.detail": "Alle hinzugefügten oder entfernten Panels sowie Größenänderungen werden verworfen. Diese Aktion kann nicht rückgängig gemacht werden.",
  "reset_overview.confirm": "Layout zurücksetzen",

  // ---------------------------------------------------------------------------
  // Overview page
  // ---------------------------------------------------------------------------
  "overview.empty": "Klicken Sie auf {{customize}}, um Panels zur Übersicht hinzuzufügen.",

  // ---------------------------------------------------------------------------
  // Auth / Login
  // ---------------------------------------------------------------------------
  "login.title": "Etherscope",
  "login.tagline": "Bitte anmelden, um fortzufahren",
  "login.username": "Benutzername",
  "login.password": "Passwort",
  "login.submit": "Anmelden",
  "login.submitting": "Anmeldung läuft…",
  "auth.loading": "Laden…",

  // ---------------------------------------------------------------------------
  // Alerts panel (AlertEventsPanel)
  // ---------------------------------------------------------------------------
  "alerts.title": "Alarme",
  "alerts.subtitle_with_rules": "{{active}}/{{total}} Regeln aktiv · Auslösungen in den letzten 24 Std.",
  "alerts.subtitle_no_rules": "Regeln · Auslösungen in den letzten 24 Std.",
  "alerts.tab.events": "Ereignisse",
  "alerts.tab.rules": "Regeln",
  "alerts.new_rule": "+ Neue Regel",
  "alerts.empty": "Keine Alarme in den letzten 24 Std.",
  "alerts.empty_no_rules": "Keine Alarme in den letzten 24 Std. — noch keine Regeln konfiguriert",
  "alerts.col.fired": "Ausgelöst",
  "alerts.col.rule": "Regel",
  "alerts.col.type": "Typ",
  "alerts.col.detail": "Detail",
  "alerts.col.delivery": "Zustellung",
  "alerts.modal.new": "Neue Alarm-Regel",
  "alerts.modal.edit": "Regel bearbeiten · {{name}}",
  "alerts.toast.created": "Regel erstellt",
  "alerts.toast.updated": "Regel aktualisiert",

  // ---------------------------------------------------------------------------
  // Alert RuleForm
  // ---------------------------------------------------------------------------
  "rule_form.label.name": "Name",
  "rule_form.label.rule_type": "Regeltyp",
  "rule_form.label.symbol": "Symbol",
  "rule_form.label.threshold_usd": "Schwellenwert (USD)",
  "rule_form.label.window_minutes": "Fenster (Minuten)",
  "rule_form.label.trigger_pct": "Auslöser in % (negativ = Abwärtsbewegung)",
  "rule_form.label.asset": "Asset",
  "rule_form.label.min_usd": "Mindest-USD",
  "rule_form.label.direction": "Richtung",
  "rule_form.label.exchange": "Exchange",
  "rule_form.label.window_hours": "Fenster (Stunden)",
  "rule_form.label.min_score": "Mindest-Smart-Score (USD)",
  "rule_form.label.cooldown": "Abklingzeit (Minuten, optional)",
  "rule_form.label.channels": "Kanäle",
  "rule_form.placeholder.name": "z. B. ETH über $4k",
  "rule_form.placeholder.cooldown": "Standard: 15 (nur Preis + Nettofluss)",
  "rule_form.rule_type_locked": "Regeltyp kann nach der Erstellung nicht mehr geändert werden",
  "rule_form.dir.any_exchange": "beliebig (eine Seite als Exchange markiert)",
  "rule_form.dir.to_exchange": "zur Exchange",
  "rule_form.dir.from_exchange": "von der Exchange",
  "rule_form.dir.net": "|Netto|",
  "rule_form.dir.inflow": "Zufluss",
  "rule_form.dir.outflow": "Abfluss",
  "rule_form.dir.any_smart": "beliebig (Smart Money auf einer Seite)",
  "rule_form.dir.from_smart": "Smart-Money-Sender (Smart Money →)",
  "rule_form.dir.to_smart": "Smart-Money-Empfänger (→ Smart Money)",
  "rule_form.channel.telegram": "Telegram",
  "rule_form.channel.webhook": "Webhook",
  "rule_form.no_channels": "Keine Kanäle — Ereignisse werden weiterhin im Dashboard protokolliert.",
  "rule_form.submit.create": "Regel erstellen",
  "rule_form.submit.save": "Änderungen speichern",
  "rule_form.submit.saving": "Speichern…",
  "rule_form.error.name_required": "Name ist erforderlich",
  "rule_form.error.webhook_url_required": "Webhook-URL ist erforderlich, wenn der Webhook-Kanal aktiviert ist",
  "rule_form.error.cooldown_invalid": "Abklingzeit muss eine nicht-negative Zahl sein",
  "rule_form.error.save_failed": "Speichern fehlgeschlagen",

  // ---------------------------------------------------------------------------
  // Alert RulesList
  // ---------------------------------------------------------------------------
  "rules_list.empty": "Noch keine Regeln — klicken Sie auf {{new_rule}}, um eine zu erstellen.",
  "rules_list.col.name": "Name",
  "rules_list.col.type": "Typ",
  "rules_list.col.condition": "Bedingung",
  "rules_list.col.channels": "Kanäle",
  "rules_list.col.cooldown": "Abklingzeit",
  "rules_list.col.enabled": "Aktiv",
  "rules_list.col.actions": "Aktionen",
  "rules_list.aria.enable": "Aktivieren",
  "rules_list.aria.disable": "Deaktivieren",
  "rules_list.confirm_delete": "Regel \"{{name}}\" löschen?",
  "rules_list.cooldown_default": "Standard",

  // ---------------------------------------------------------------------------
  // Wallet drawer (WalletDrawer)
  // ---------------------------------------------------------------------------
  "wallet.drawer.heading": "Wallet",
  "wallet.etherscan_link": "Etherscan ↗",
  "wallet.aria.close": "Schließen",
  "wallet.unavailable": "Nicht verfügbar — bitte erneut versuchen",
  "wallet.section.address": "Adresse",
  "wallet.section.current_balance": "Aktuelles Guthaben",
  "wallet.balance_history_unavailable": "Guthaben-Verlauf nicht verfügbar — RPC-Endpunkt nicht konfiguriert.",
  "wallet.section.active_since": "Aktiv seit",
  "wallet.section.last_seen": "Zuletzt gesehen",
  "wallet.section.tx_count": "Transaktionsanzahl",
  "wallet.section.token_holdings": "Token-Bestände",
  "wallet.token_holdings.subtitle": "· Top {{count}} nach USD",
  "wallet.section.net_flow": "Nettofluss · 7 Tage (Wal-Transfers)",
  "wallet.section.top_counterparties": "Top-Gegenparteien · 30 Tage",
  "wallet.counterparties.empty": "Keine Wal-großen Gegenparteien in den letzten 30 Tagen.",
  "wallet.section.recent_activity": "Aktuelle Wal-Aktivität",
  "wallet.recent_activity.empty": "Keine Transfers über dem Wal-Schwellenwert mit dieser Adresse. Die Wallet kann in kleineren Transaktionen weiterhin aktiv sein.",
  "wallet.section.linked_wallets": "Verknüpfte Wallets ({{count}})",
  "wallet.below_threshold": "Diese Wallet liegt unter dem Wal-Tracking-Schwellenwert (≥100 ETH oder ≥$250k Stables pro Transfer). Das Profil zeigt nur das On-Chain-Guthaben — kleinere Transaktionen werden nicht indiziert.",
  "wallet.netflow.no_moves": "Keine Wal-Transfers in 7 Tagen",
  "wallet.netflow.active_days": "{{count}} von 7 Tagen aktiv",
  "wallet.score.title": "Wallet-Score · 30 Tage",
  "wallet.score.realized_pnl": "Realisierter PnL",
  "wallet.score.win_rate": "Win Rate",
  "wallet.score.volume": "Volumen",
  "wallet.score.updated": "aktualisiert {{age}}",
  "wallet.score.swaps": "{{count}} Swaps · v1 Score = realisierter PnL",
  "wallet.score.smart_badge_title": "Smart-Money-Tier {{tier}}",
  "wallet.token.unpriced": "kein Preis",
  "wallet.transfer.open_tx": "Transaktion auf Etherscan öffnen",

  // ---------------------------------------------------------------------------
  // Whale transfers panel (WhaleTransfersPanel)
  // ---------------------------------------------------------------------------
  "whale-transfers.title": "Wal-Transfers",
  "whale-transfers.subtitle": "{{count}} Transaktionen · {{total}} gesamt · letzte {{hours}} Std.",
  "whale-transfers.subtitle_with_smart": "{{count}} Transaktionen · {{total}} gesamt · letzte {{hours}} Std. · {{smart}} Smart Money",
  "whale-transfers.subtitle_default": "ETH ≥ 500 · Stables ≥ $1M",
  "whale-transfers.smart_only": "★ Nur Smart Money",
  "whale-transfers.smart_only_title": "Nur Transfers anzeigen, bei denen Wallets einen 30-Tage-realisierten PnL ≥ $100k aufweisen",
  "whale-transfers.aria.asset_filter": "Nach Asset filtern",
  "whale-transfers.filter.clear": "Zurücksetzen",
  "whale-transfers.pending_label": "Ausstehend ({{count}})",
  "whale-transfers.empty_smart": "Keine Smart-Money-Transaktionen in den letzten {{hours}} Std. — ★ deaktivieren, um alle Wale zu sehen",
  "whale-transfers.empty": "Noch keine Wal-Transfers — Listener benötigt ALCHEMY_API_KEY und einige Blöcke",
  "whale-transfers.col.time": "Zeit",
  "whale-transfers.col.asset": "Asset",
  "whale-transfers.col.from": "Von",
  "whale-transfers.col.to": "An",
  "whale-transfers.col.amount": "Betrag",
  "whale-transfers.col.usd": "USD",
  "whale-transfers.col.tx": "Tx",
  "whale-transfers.open_etherscan": "In Etherscan öffnen",

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
  "mempool.title": "Mempool-Wale",
  "mempool.subtitle": "{{count}} ausstehend · {{total}} unbestätigt · {{gas}} gwei Median",
  "mempool.subtitle_empty": "Live ausstehende Wal-Transaktionen vom lokalen Node",
  "mempool.subtitle_no_gas": "{{count}} ausstehend · {{total}} unbestätigt",
  "mempool.empty": "Derzeit keine ausstehenden Wale — benötigt einen selbst gehosteten Node (ALCHEMY_WS_URL); Wale erscheinen innerhalb von Sekunden nach Broadcast",
  "mempool.col.age": "Alter",
  "mempool.col.asset": "Asset",
  "mempool.col.from": "Von",
  "mempool.col.to": "An",
  "mempool.col.amount": "Betrag",
  "mempool.col.usd": "USD",
  "mempool.col.gas": "Gas",
  "mempool.col.tx": "Tx",

  // ---------------------------------------------------------------------------
  // Network activity panel (NetworkActivityPanel)
  // ---------------------------------------------------------------------------
  "network-activity.title": "Netzwerk-Aktivität",
  "network-activity.subtitle_live": "letzter Block {{time}}",
  "network-activity.subtitle_empty": "Block-Statistiken · benötigt ALCHEMY_API_KEY",
  "network-activity.stat.gas_price": "Gas-Preis",
  "network-activity.stat.base_fee": "Basisgebühr",
  "network-activity.stat.block_time": "Blockzeit",
  "network-activity.stat.tx_per_block": "Tx / Block",
  "network-activity.empty": "Noch keine Netzwerkdaten — Realtime-Listener muss mit gültigem ALCHEMY_API_KEY laufen",
  "network-activity.chart.gas": "Gas (gwei)",
  "network-activity.chart.tx": "Transaktionen pro Block",

  // ---------------------------------------------------------------------------
  // Price hero (PriceHero)
  // ---------------------------------------------------------------------------
  "price-hero.mainnet": "· Mainnet",
  "price-hero.24h_high": "24-Std.-Hoch",
  "price-hero.24h_low": "24-Std.-Tief",
  "price-hero.24h_volume": "24-Std.-Volumen",
  "price-hero.24h_change": "24-Std.-Veränderung",
  "price-hero.range.low": "Tief",
  "price-hero.range.high": "Hoch",

  // ---------------------------------------------------------------------------
  // Price chart (PriceChart)
  // ---------------------------------------------------------------------------
  "price-chart.title": "ETH / USDT",
  "price-chart.subtitle_loading": "Laden…",
  "price-chart.subtitle_error": "Chart nicht verfügbar",
  "price-chart.subtitle_disconnected": "{{count}} {{tf}} Kerzen · Live getrennt — Wiederverbindung läuft",
  "price-chart.subtitle_live": "{{count}} {{tf}} Kerzen · Binance Live",

  // ---------------------------------------------------------------------------
  // Derivatives panel (DerivativesPanel)
  // ---------------------------------------------------------------------------
  "derivatives.title": "Derivatives",
  "derivatives.subtitle": "OI + Funding Rates · ETH Perp · Binance / Bybit / OKX / Deribit",
  "derivatives.empty": "Noch keine Derivatives-Daten — Worker läuft einmal pro Stunde. Erste Synchronisierung beim Worker-Start; in ca. 60 Sek. erneut prüfen.",
  "derivatives.chart.funding": "Funding Rate",
  "derivatives.chart.oi": "Open Interest (USD)",
  "derivatives.pill.funding": "Funding",
  "derivatives.pill.oi": "OI",

  // ---------------------------------------------------------------------------
  // Liquidations panel (LiquidationsPanel)
  // ---------------------------------------------------------------------------
  "liquidations.title": "Liquidations",
  "liquidations.subtitle": "Perp Futures · ETH-USD · {{venue}}",
  "liquidations.tile.longs": "Long-Liquidations",
  "liquidations.tile.shorts": "Short-Liquidations",
  "liquidations.tile.skew": "Skew · größte",
  "liquidations.skew_pct": "{{pct}}% long",
  "liquidations.largest": "größte {{value}}",
  "liquidations.positions_count": "{{count}} Positionen",
  "liquidations.empty": "Keine Liquidations in den letzten {{range}} — ruhige Marktphase. Listener abonniert Bybit's allLiquidation.ETHUSDT; Ereignisse erscheinen in Echtzeit.",

  // ---------------------------------------------------------------------------
  // On-chain perps panel (OnchainPerpsPanel)
  // ---------------------------------------------------------------------------
  "onchain-perps.title": "On-Chain-Perps",
  "onchain-perps.subtitle": "GMX V2 · Arbitrum",
  "onchain-perps.tab.events": "Ereignisse",
  "onchain-perps.tab.liquidations": "Liquidations",
  "onchain-perps.tab.positions": "Offene Positionen",
  "onchain-perps.filter.kind": "Typ",
  "onchain-perps.filter.min_size": "Mindestgröße",
  "onchain-perps.filter.any": "beliebig",
  "onchain-perps.events.empty": "Keine Ereignisse in den letzten 24 Std. für diesen Filter — Arbitrum-Listener wird ggf. noch initialisiert, falls das Deployment neu ist.",
  "onchain-perps.liq.empty": "Keine Liquidations in 24 Std.",
  "onchain-perps.positions.empty": "Noch keine offenen Positionen.",
  "onchain-perps.tile.longs_liq": "Long-Liquidations",
  "onchain-perps.tile.shorts_liq": "Short-Liquidations",
  "onchain-perps.tile.open_skew": "Offener Skew",
  "onchain-perps.tile.events_sub": "{{count}} Ereignisse 24 Std.",
  "onchain-perps.tile.biggest_sub": "größte {{value}}",
  "onchain-perps.col.when": "Zeitpunkt",
  "onchain-perps.col.account": "Konto",
  "onchain-perps.col.market": "Markt",
  "onchain-perps.col.kind": "Typ",
  "onchain-perps.col.side": "Seite",
  "onchain-perps.col.size": "Größe",
  "onchain-perps.col.lev": "Hebel",
  "onchain-perps.col.price": "Preis",
  "onchain-perps.col.pnl": "PnL",
  "onchain-perps.col.opened": "Eröffnet",

  // ---------------------------------------------------------------------------
  // Smart money direction panel (SmartMoneyDirectionPanel)
  // ---------------------------------------------------------------------------
  "smart-money-direction.title": "Smart-Money-Richtung",
  "smart-money-direction.subtitle": "Letzte 24 Std. · 30-Tage-realisierter PnL ≥ {{min}}",
  "smart-money-direction.empty": "Keine Smart-Money-DEX-Swaps in den letzten 24 Std. — der tägliche score_wallets-Cron erzeugt diesen Datensatz; das Panel befüllt sich beim ersten Durchlauf.",
  "smart-money-direction.verdict.buying": "Netto-Kauf",
  "smart-money-direction.verdict.selling": "Netto-Verkauf",
  "smart-money-direction.verdict.balanced": "Ausgewogen",
  "smart-money-direction.wallets_active": "{{count}} Smart Wallet aktiv",
  "smart-money-direction.wallets_active_plural": "{{count}} Smart Wallets aktiv",
  "smart-money-direction.tile.bought": "Gekauft",
  "smart-money-direction.tile.sold": "Verkauft",
  "smart-money-direction.net_7d": "Netto · 7 Tage",

  // ---------------------------------------------------------------------------
  // Smart money leaderboard (SmartMoneyLeaderboard)
  // ---------------------------------------------------------------------------
  "smart-money.title": "Smart-Money-Rangliste",
  "smart-money.subtitle": "Top 50 ETH DEX-Trader nach 30-Tage-realisiertem PnL · nur WETH · Mainnet",
  "smart-money.empty": "Noch kein Snapshot — Aktualisierung läuft täglich um 03:00 UTC. Benötigt DUNE_QUERY_ID_SMART_MONEY_LEADERBOARD.",
  "smart-money.stale": "Snapshot ist älter als {{hours}} Std. — tägliche Aktualisierung möglicherweise unterbrochen.",
  "smart-money.col.rank": "#",
  "smart-money.col.wallet": "Wallet",
  "smart-money.col.realized_pnl": "Realisierter PnL",
  "smart-money.col.unrealized": "Unrealisiert",
  "smart-money.col.win_rate": "Win Rate",
  "smart-money.col.trades": "Trades",
  "smart-money.col.volume": "Volumen",

  // ---------------------------------------------------------------------------
  // Market regime panel (MarketRegimePanel)
  // ---------------------------------------------------------------------------
  "market-regime.title": "Markt-Regime",
  "market-regime.subtitle": "Regelbasiert · 6-Merkmal-Score · stündliche Aktualisierung",
  "market-regime.score_confidence": "Score · Konfidenz",
  "market-regime.hint.euphoria": "Extreme Baisse — Hebel überdehnt",
  "market-regime.hint.distribution": "Leichte Baisse-Tendenz",
  "market-regime.hint.neutral": "Keine ausgeprägte Richtungstendenz",
  "market-regime.hint.accumulation": "Leichte Hausse-Tendenz",
  "market-regime.hint.capitulation": "Extreme Hausse — Angst-Ausverkauf",

  // ---------------------------------------------------------------------------
  // CEX net flow panel (CexNetFlowPanel)
  // ---------------------------------------------------------------------------
  "cex-net-flow.title": "CEX-Nettofluss",
  "cex-net-flow.subtitle": "Live · Wal ETH + Stables ein-/ausgehend bei Exchanges",
  "cex-net-flow.empty": "Noch keine CEX-klassifizierten Wal-Transfers — Listener befüllt sich, sobald neue Wal-Transaktionen zu/von Exchange-Hot-Wallets eintreffen.",
  "cex-net-flow.verdict.balanced": "Ausgewogen",
  "cex-net-flow.verdict.inflow": "Netto-Zufluss",
  "cex-net-flow.verdict.outflow": "Netto-Abfluss",
  "cex-net-flow.largest_inflow": "Größter Einzelzufluss",
  "cex-net-flow.largest_outflow": "Größter Einzelabfluss",

  // ---------------------------------------------------------------------------
  // Category net flow panel (CategoryNetFlowPanel)
  // ---------------------------------------------------------------------------
  "category-net-flow.title": "DeFi-Flüsse",
  "category-net-flow.subtitle": "Live · Wal-Transaktionen in/aus DEX, Lending, Staking, Bridges",
  "category-net-flow.empty": "Noch keine klassifizierten Transfers — Listener befüllt sich, sobald Wal-Transaktionen zu/von DeFi-Contracts eintreffen.",
  "category-net-flow.moves_singular": "{{count}} Transaktion",
  "category-net-flow.moves_plural": "{{count}} Transaktionen",

  // ---------------------------------------------------------------------------
  // Exchange flows panel (ExchangeFlowsPanel)
  // ---------------------------------------------------------------------------
  "exchange-flows.title": "Exchange-Nettoflüsse",
  "exchange-flows.subtitle": "letzte {{range}} · Dune · beschriftete CEX-Wallets",
  "exchange-flows.empty": "Noch keine Daten — warte auf Dune-Synchronisierung",
  "exchange-flows.row.in": "ein {{value}}",
  "exchange-flows.row.out": "aus {{value}}",

  // ---------------------------------------------------------------------------
  // Order flow panel (OrderFlowPanel)
  // ---------------------------------------------------------------------------
  "order-flow.title": "Order Flow",
  "order-flow.subtitle": "DEX Kauf- vs. Verkaufsdruck · ETH (WETH) · letzte {{range}}",
  "order-flow.empty": "Noch keine Daten — warte auf Dune Order-Flow-Sync (erster Durchlauf beim Worker-Start, dann alle 8 Std.). Benötigt DUNE_QUERY_ID_ORDER_FLOW.",
  "order-flow.tile.buy": "Kaufvolumen",
  "order-flow.tile.sell": "Verkaufsvolumen",
  "order-flow.tile.net": "Nettodruck",
  "order-flow.tile.trades": "{{count}} Trades",
  "order-flow.by_dex": "Nach DEX · letzte {{range}}",

  // ---------------------------------------------------------------------------
  // Mantle order flow panel (MantleOrderFlowPanel)
  // ---------------------------------------------------------------------------
  "mantle-order-flow.title": "Mantle Order Flow (24 Std.)",
  "mantle-order-flow.subtitle": "MNT Kauf-/Verkaufsdruck auf Agni",
  "mantle-order-flow.empty": "Noch keine Daten — MANTLE_WS_URL setzen und das Mantle-Docker-Compose-Profil starten.",
  "mantle-order-flow.tile.buy": "Kaufvolumen",
  "mantle-order-flow.tile.sell": "Verkaufsvolumen",
  "mantle-order-flow.tile.net": "Nettodruck",
  "mantle-order-flow.price_unavailable": "USD-Preisgestaltung nicht verfügbar (CoinGecko); Chart zeigt MNT-denominierte Balken, wenn erreichbar.",

  // ---------------------------------------------------------------------------
  // Volume structure panel (VolumeStructurePanel)
  // ---------------------------------------------------------------------------
  "volume-structure.title": "Volumen-Struktur",
  "volume-structure.subtitle": "DEX-Volumen nach Handelsgröße · ETH (WETH) · letzte {{range}}",
  "volume-structure.empty": "Noch keine Daten — benötigt DUNE_QUERY_ID_VOLUME_BUCKETS; erster Sync beim Worker-Start, dann alle 8 Std.",
  "volume-structure.tile.share": "{{pct}}% Anteil",

  // ---------------------------------------------------------------------------
  // Stablecoin supply panel (StablecoinSupplyPanel)
  // ---------------------------------------------------------------------------
  "stablecoin-supply.title": "Stablecoin-Umlauf Δ",
  "stablecoin-supply.subtitle": "letzte {{range}} · Mint vs. Burn",
  "stablecoin-supply.empty": "Noch keine Daten — warte auf Dune-Synchronisierung",
  "stablecoin-supply.row.mint_burn": "Mint {{mint}} / Burn {{burn}}",
  "stablecoin-supply.group_label": "{{peg}}-Stables",

  // ---------------------------------------------------------------------------
  // Live volume panel (LiveVolumePanel)
  // ---------------------------------------------------------------------------
  "live-volume.title": "Live On-Chain-Volumen",
  "live-volume.subtitle": "Stables · pro Minute · {{minutes}}m Fenster · ~5s Aktualisierung",
  "live-volume.empty": "Noch keine Daten — Realtime-Listener wartet auf neue Blöcke",
  "live-volume.minutes_shown": "{{count}} Minuten angezeigt",
  "live-volume.window_total": "{{total}} Fenstergröße gesamt",

  // ---------------------------------------------------------------------------
  // Onchain volume panel (OnchainVolumePanel)
  // ---------------------------------------------------------------------------
  "onchain-volume.title": "On-Chain-Transfervolumen",
  "onchain-volume.subtitle": "gestapeltes tägliches USD · live · abgeleitet vom Realtime-Listener",
  "onchain-volume.empty": "Noch keine Daten — warte auf den Realtime-Listener.",

  // ---------------------------------------------------------------------------
  // Staking flows panel (StakingFlowsPanel)
  // ---------------------------------------------------------------------------
  "staking-flows.title": "Beacon-Flüsse",
  "staking-flows.subtitle": "letzte {{range}} · Staking-Einzahlungen vs. Validator-Exits",
  "staking-flows.empty": "Noch keine Daten — warte auf Dune-Synchronisierung",
  "staking-flows.total_staked": "Gesamt gestaktes ETH",
  "staking-flows.active_validators": "{{count}} aktive Validatoren",
  "staking-flows.active_validators_dash": "aktive Validatoren —",
  "staking-flows.leg.deposits": "Einzahlungen",
  "staking-flows.leg.full_exits": "Vollständige Exits",
  "staking-flows.partial_withdrawals": "Rewards-Skim (teilweise Auszahlungen):",
  "staking-flows.by_issuer": "Nach Emittent ({{range}})",
  "staking-flows.col.deposits": "Einzahlungen",
  "staking-flows.col.exits": "Exits",
  "staking-flows.col.net": "Netto",

  // ---------------------------------------------------------------------------
  // LST market share panel (LstMarketSharePanel)
  // ---------------------------------------------------------------------------
  "lst-market-share.title": "LST-Marktanteil",
  "lst-market-share.subtitle": "letzte {{range}} · ETH-äquivalentes Angebot pro Token",
  "lst-market-share.empty": "Noch keine Daten — warte auf erste stündliche Synchronisierung",
  "lst-market-share.apr_label": "APR",

  // ---------------------------------------------------------------------------
  // LRT TVL panel (LrtTvlPanel)
  // ---------------------------------------------------------------------------
  "lrt-tvl.title": "LRT-Emittenten",
  "lrt-tvl.subtitle": "Liquid Restaking · Ethereum Mainnet · DefiLlama",
  "lrt-tvl.empty": "Noch keine Daten — erste stündliche Synchronisierung ausstehend",
  "lrt-tvl.total": "{{value}} gesamt",

  // ---------------------------------------------------------------------------
  // DeFi TVL panel (DefiTvlPanel)
  // ---------------------------------------------------------------------------
  "defi-tvl.title": "DeFi TVL",
  "defi-tvl.subtitle": "Ethereum Mainnet · gesperrte Bestände pro Protokoll · DefiLlama",
  "defi-tvl.empty": "Noch keine Daten — erste stündliche Synchronisierung ausstehend",
  "defi-tvl.locked": "{{value}} gesperrt",
  "defi-tvl.more_assets": "+ {{count}} weitere Assets · {{value}} kombiniert",
  "defi-tvl.aria.select_protocol": "DeFi-Protokoll auswählen",

  // ---------------------------------------------------------------------------
  // DEX pool TVL panel (DexPoolTvlPanel)
  // ---------------------------------------------------------------------------
  "dex-pool-tvl.title": "DEX-Pool-TVL",
  "dex-pool-tvl.subtitle": "Ethereum Mainnet · Top {{n}} Pools nach TVL · DefiLlama",
  "dex-pool-tvl.empty": "Noch keine Daten — erste stündliche Synchronisierung ausstehend",
  "dex-pool-tvl.pools_shown": "{{count}} Pools angezeigt",
  "dex-pool-tvl.combined": "{{value}} kombiniert",
  "dex-pool-tvl.aria.filter": "Nach DEX filtern",

  // ---------------------------------------------------------------------------
  // Bridge flows panel (BridgeFlowsPanel)
  // ---------------------------------------------------------------------------
  "bridge-flows.title": "Bridge-Flüsse",
  "bridge-flows.subtitle": "L1 ↔ L2 · letzte {{range}} · Arbitrum / Base / Optimism / zkSync",
  "bridge-flows.empty": "Noch keine Daten — warte auf erste Dune-Synchronisierung",
  "bridge-flows.deposit_withdraw": "Einzahlung {{deposit}} / Abhebung {{withdraw}}",
  "bridge-flows.net_l1_to_l2": "L1 → L2",
  "bridge-flows.net_l2_to_l1": "L2 → L1",

  // ---------------------------------------------------------------------------
  // Onchain page section headings
  // ---------------------------------------------------------------------------
  "section.stablecoins": "Stablecoins",
  "section.staking": "Staking",
  "section.defi": "DeFi",
  "section.bridges": "Bridges (L1↔L2)",
  "section.network": "Netzwerk",
  "section.other": "Sonstiges",
};
