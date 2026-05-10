# i18n Glossary

Reference for translators authoring `frontend/src/i18n/de.ts` (and any
future locale files). Updated as new domain terms appear.

## Stays in English regardless of locale

These are crypto/finance jargon that German finance audiences read in
English. Translating them produces awkward output (e.g. "Smart-Geld").

- **Asset symbols:** USDT, USDC, USDS, DAI, PYUSD, FDUSD, GHO, EUROC,
  ZCHF, EURCV, EURe, tGBP, USDe, XSGD, BRZ, EURS, WETH, ETH, BTC, MNT,
  mETH, stETH, rETH, cbETH, sfrxETH, swETH, ETHx
- **DEX names:** Uniswap V2, Uniswap V3, Curve, Balancer, Sushi,
  Pancake, Maverick, Agni, FusionX, Cleopatra, Butter, Merchant Moe
- **CEX names:** Binance, Bybit, OKX, Deribit, Coinbase, Kraken
- **Concept terms:** Smart money, OI (Open Interest), TVL, LST, LRT,
  liquidation, slippage, MEV, mempool, perp, perpetual, futures,
  forceOrder, allLiquidation, long, short, basis
- **Identifiers:** addresses (0x…), tx hashes, block numbers
- **Numeric values + units:** percentages, USD, ETH, gwei, gas

## Standard German translations

For terms we DO translate, use these consistently:

| English | German |
|---|---|
| Whale | Wal |
| Whale transfer | Wal-Transfer |
| Alert | Alarm |
| Alert rule | Alarm-Regel |
| Overview | Übersicht |
| Markets | Märkte |
| Onchain | On-Chain (hyphenated) |
| Mempool | Mempool (kept as proper noun) |
| Network activity | Netzwerk-Aktivität |
| Settings | Einstellungen |
| Save / Cancel | Speichern / Abbrechen |
| Loading | Laden |
| Unavailable | Nicht verfügbar |
| Buy / Sell / Net | Kauf / Verkauf / Netto |
| Quiet market window | ruhige Marktphase |
| Transfer | Transfer (kept) |
| Pending | Ausstehend |
| Price | Preis |
| Volume | Volumen |
| Holdings | Bestände |
| Linked wallets | Verknüpfte Wallets |
| Cluster / Counterparty | Cluster / Gegenpartei |
| Smart only (toggle) | Nur Smart Money |
| no data yet | noch keine Daten |
| no liquidations in the last 24h | keine Liquidationen in den letzten 24 Std. |
| 24h | 24 Std. |
| Last update / event | Letzte Aktualisierung / Ereignis |

## Tone guidelines

- Use formal German ("Sie", not "Du"). The audience is institutional /
  professional traders.
- Prefer compact compound nouns where natural ("Netzwerk-Aktivität",
  not "Aktivität des Netzwerks").
- Use the German period (".") as the thousands separator only in prose;
  the numeric formatting in the dashboard stays English-locale (commas).

## How translators use this file

When unsure about a term, check the table above first. If a new term
isn't listed, add it here in the same PR as the translation, so the
next translator (or a future audit) sees the decision.
