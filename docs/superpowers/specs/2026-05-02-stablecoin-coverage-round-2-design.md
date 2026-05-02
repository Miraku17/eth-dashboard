# Stablecoin Coverage Round 2 — Design

**Status:** approved 2026-05-02
**Track:** v2 follow-up (extends the round-1 stablecoin coverage)
**Related specs:**
- `2026-05-01-stablecoin-coverage-design.md` (parent — established the StableToken / FX / Dune-asset_alias machinery)

## Goal

Extend whale-tracking + stablecoin-supply coverage from the 9 stables shipped in PR #21 to **12 total** by adding three more contracts that real Dune diagnostic data confirmed are active on Ethereum mainnet:

- **EURCV** (Société Générale's EUR coin) — 78,009 transfers / 175 mints / 26 burns over 30d. Much more active than originally guessed.
- **EURe** (Monerium EUR — bonus, wasn't in the client's original list) — 4,192 transfers / 498 mints / 611 burns over 30d. The most active EUR mint/burn we found on chain. Regulated EU bank-issued stablecoin.
- **tGBP** (TrueGBP) — 309 transfers / 15 mints / 1 burn. Small but real GBP-pegged supply.

Three other deferred coins (EUROS, EURS Stasis, BRZ) remain skipped — diagnostic confirmed they have effectively zero ETH activity. XSGD also remains optional/skipped for round 2 (real volume but only 5 mint/burn events in 30d).

## Non-goals

- The 4 confirmed-inactive coins (EUROS, EURS Stasis, BRZ, XSGD) — skipped per diagnostic data.
- Any architectural change. Round 1's `StableToken` dataclass + parser FX path + Dune `asset_alias` CTE all already handle non-USD pegs and contract-address filters.
- New Dune query, new schema, new env var, new tests beyond the unit pattern from round 1.

## Verified contract metadata (from Dune `tokens.erc20`)

| Symbol | Contract address | Decimals | Peg | `price_usd_approx` |
|---|---|---|---|---|
| EURCV | `0x5f7827fdeb7c20b443265fc2f40845b715385ff2` | 18 | EUR | 1.08 |
| EURe | `0x39b8b6385416f4ca36a20319f70d28621895279d` | 18 | EUR | 1.08 |
| tGBP | `0x27f6c8289550fce67f6b50bed1f519966afe5287` | 18 | GBP | 1.27 |

All three have non-zero supply, real ERC-20 metadata, and active Ethereum presence verified via direct Dune diagnostic queries on 2026-05-02.

## What changes

Five files, all extension-shaped:

1. **`backend/app/realtime/tokens.py`** — append three `StableToken` entries to `STABLES`.
2. **`backend/app/api/schemas.py`** — extend the `WhaleAsset` Literal with `"EURCV"`, `"EURe"`, `"tGBP"`.
3. **`backend/dune/stablecoin_supply.sql`** — extend the `asset_alias` CTE with three rows (Dune query 7362750 also gets updated via MCP so it picks up the new contracts on the next sync).
4. **`frontend/src/api.ts`** — extend the `WhaleAsset` TS literal.
5. **`frontend/src/components/WhaleTransfersPanel.tsx`** — extend `ASSET_OPTIONS` dropdown with three entries.

CLAUDE.md M3 milestone description updated to reflect 12 stables instead of 9.

## Symbol casing

Note: EURe and tGBP use mixed case (lowercase `e` and lowercase `t`). The actual ERC-20 `symbol()` returns those exact strings. Our backend `WhaleAsset` Literal will store them with the case they're known by; the frontend dropdown displays them unchanged. The Dune `asset_alias` CTE outputs the same casing so cache keys match.

## Tests

One additional parser test (sanity that EURCV/EURe/tGBP threshold at the right USD notional). Existing tests for EUROC + ZCHF FX path continue to verify the FX machinery — no need to repeat.

## Risks / known limits

- **Symbol-naming consistency** between parser, schema, frontend, Dune. We've already handled "EUROC ≠ EURC" via Dune's contract-address filter. Same approach extends here.
- **EURCV is fast-growing** (SocGen-issued EU bank coin, ~$5M when first checked weeks ago, now showing ~78k transfers in 30d) — may warrant a higher whale threshold once it scales further. Out of scope for this round.
- **tGBP is small** (309 transfers) — whale events will be infrequent. Documented as expected.

## Future work (round 3+)

- Re-evaluate the deferred coins (XSGD, EUROS, EURS, BRZ) annually — issuer activity changes.
- Consider live FX-rate refresh from CoinGecko if currency drift becomes visible (>10%).
- Expand to non-EU/UK/CH currencies if the operator's portfolio pivots (BRL, JPY, etc.).
