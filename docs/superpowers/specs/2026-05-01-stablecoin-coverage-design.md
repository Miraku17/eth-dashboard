# Stablecoin Coverage Expansion — Design

**Status:** approved 2026-05-01
**Track:** v2 follow-up — extending the data layer
**Related specs:**
- `2026-04-23-eth-analytics-dashboard-design.md` (root)

## Goal

Extend whale-tracking, stablecoin-supply, and exchange-flow coverage from
the current 3 USD stables (USDT, USDC, DAI) to **9 stables total** by
adding 4 USD-pegged and 2 non-USD-pegged tokens with confirmed Ethereum
mainnet contracts and visible supply:

- **PYUSD** — PayPal USD ($1, ~$1B supply)
- **FDUSD** — First Digital USD ($1, ~$1B supply)
- **USDS** — Sky/Maker's flagship ($1, replacing DAI)
- **GHO** — Aave's stablecoin ($1, ~$200M supply)
- **EUROC** — Circle EUR Coin (€1, ~$50M supply)
- **ZCHF** — Frankencoin (CHF1, ~$30M supply)

Non-USD coins use FX-aware thresholds so a whale event from a EUROC
transfer is correctly compared to the same USD notional as a USDT
transfer.

## Non-goals

- **The other 5 deferred coins** (EURCV, EUROS, BRZ, XSGD, tGBP) are
  NOT shipped this round. Reason: ambiguous tickers (EUROS, tGBP map
  to multiple unrelated tokens) or low/wrong-chain supply (BRZ, XSGD
  primarily on Polygon/BSC; EURCV ~$5M on ETH). Adding them later is
  one PR per coin once the operator confirms specific contract
  addresses.
- **Live FX-rate fetching.** Rates for EUR/CHF→USD are hardcoded as
  `price_usd_approx` per token (refresh-on-PR-bump pattern) — same
  approach already used by volatile tokens (WETH, WBTC, LINK, etc.).
  Whale-detection isn't sensitive to ±10% drift; a CHF1 ≈ $1.10
  threshold compared as $1.00 still surfaces real whales.
- **Backend FX provider integration.** No CoinGecko FX endpoint
  hookup, no Redis FX cache. The price hint lives in the token
  registry alongside existing `VolatileToken.price_usd_approx`.
- **Adding stablecoins to the order-flow / volume-buckets / DEX
  panels.** Those operate on WETH, not on the stable side. Out of
  scope.
- **Per-stablecoin charts.** No new panels. The new coins flow into
  the existing Whale Transfers panel + StablecoinSupply panel.

## UX

- **Whale Transfers panel** — when a tracked transfer of any of the 6
  new stables crosses the USD threshold (`WHALE_STABLE_THRESHOLD_USD`),
  it appears in the live whale list with the stablecoin's symbol
  (`PYUSD`, `FDUSD`, `USDS`, `GHO`, `EUROC`, `ZCHF`) and correct USD
  notional.
- **Whale Transfers asset filter** — the dropdown gains 6 new options.
  `ANY` continues to mean "any tracked stable + ETH + tracked
  volatile." Filtering by `EUROC` shows only EUROC transfers, etc.
- **StablecoinSupplyPanel** — once the Dune query is updated and
  re-saved (operator action; see "Operator setup" below), supply
  series render for the new coins automatically.
- **Address drawer (wallet clustering)** — already address-based, no
  per-coin work needed.

No new panels, no UI redesign.

## Token registry change

Today `STABLES` is `tuple[Token, ...]` where `Token` has only `symbol`,
`address`, `decimals`. Stable transfers use `amount == usd_value`
because USD pegs are assumed.

Change: replace the `Token` dataclass for stables with a new
`StableToken` that carries the USD-conversion hint:

```python
@dataclass(frozen=True)
class StableToken:
    symbol: str
    address: str          # lowercase 0x…
    decimals: int
    peg_currency: str     # "USD" | "EUR" | "CHF" (display only)
    price_usd_approx: float  # 1.0 for USD pegs; ~1.08 for EUR; ~1.10 for CHF
```

USD-pegged entries get `peg_currency="USD"`, `price_usd_approx=1.0`.
Non-USD entries (EUROC, ZCHF) carry the actual rate.

The new `STABLES` tuple:

```python
STABLES: tuple[StableToken, ...] = (
    StableToken("USDT",  "0xdac17f958d2ee523a2206206994597c13d831ec7", 6,  "USD", 1.00),
    StableToken("USDC",  "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6,  "USD", 1.00),
    StableToken("DAI",   "0x6b175474e89094c44da98b954eedeac495271d0f", 18, "USD", 1.00),
    StableToken("PYUSD", "0x6c3ea9036406852006290770bedfcaba0e23a0e8", 6,  "USD", 1.00),
    StableToken("FDUSD", "0xc5f0f7b66764f6ec8c8dff7ba683102295e16409", 18, "USD", 1.00),
    StableToken("USDS",  "0xdc035d45d973e3ec169d2276ddab16f1e407384f", 18, "USD", 1.00),
    StableToken("GHO",   "0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f", 18, "USD", 1.00),
    StableToken("EUROC", "0x1abaea1f7c830bd89acc67ec4af516284b1bc33c", 6,  "EUR", 1.08),
    StableToken("ZCHF",  "0xb58e61c3098d85632df34eecfb899a1ed80921cb", 18, "CHF", 1.10),
)
```

Decimals verified: USDT/USDC/PYUSD/EUROC use 6 (Circle/Tether/PayPal
convention); DAI/FDUSD/USDS/GHO/ZCHF use 18 (Maker/Aave/Frankencoin
convention).

## Parser change

`backend/app/realtime/parser.py::parse_erc20_log` currently has a
USD-pegged-only path:

```python
if stable is not None:
    amount = raw / (10**stable.decimals)
    if amount < threshold_usd:
        return None
    return WhaleTransfer(... amount=amount, usd_value=amount, ...)
```

Becomes:

```python
if stable is not None:
    amount = raw / (10**stable.decimals)
    usd = amount * stable.price_usd_approx
    if usd < threshold_usd:
        return None
    return WhaleTransfer(... amount=amount, usd_value=usd, ...)
```

The threshold compare moves from `amount` to `usd`. For USD pegs
nothing changes (`price_usd_approx=1.0`). For EUROC/ZCHF the threshold
is now applied to the correct USD notional.

The pending-transaction path in the same module has the same shape;
parallel update.

## API schema change

`backend/app/api/schemas.py`:

```python
WhaleAsset = Literal["ETH", "USDT", "USDC", "DAI", "ANY"]
```

Becomes:

```python
WhaleAsset = Literal[
    "ETH",
    "USDT", "USDC", "DAI",
    "PYUSD", "FDUSD", "USDS", "GHO", "EUROC", "ZCHF",
    "ANY",
]
```

Used in two whale-transfer endpoint params (`/api/whales/transfers`
and `/api/whales/pending`); both pick up the new options
automatically.

## Frontend change

`frontend/src/components/WhaleTransfersPanel.tsx` has a hardcoded
asset-filter dropdown. Today the options are `ANY`, `ETH`, `USDT`,
`USDC`, `DAI`. Add the 6 new options in registry order so the
dropdown order matches the backend literal.

`frontend/src/api.ts` has the corresponding `WhaleAsset` TypeScript
type literal — kept in sync with the backend by hand. Add the same
6 entries.

No other frontend changes; `<AssetBadge>` (the chip rendered next
to each whale row's amount) reads the symbol from the API response,
so it auto-renders for any new symbol.

## Stablecoin-supply Dune query

`backend/dune/stablecoin_supply.sql` has this clause:

```sql
and symbol in ('USDT','USDC','DAI')
```

Becomes:

```sql
and symbol in ('USDT','USDC','DAI','PYUSD','FDUSD','USDS','GHO','EUROC','ZCHF')
```

(Both `mints` and `burns` CTEs.)

The Dune query lives in our repo as the source of truth, but the
operator pastes it into Dune and re-saves under the existing
`DUNE_QUERY_ID_STABLECOIN_SUPPLY`. The next worker cron picks up the
expanded result set and writes additional rows to `stablecoin_flows`
keyed by symbol — no schema change.

The frontend `<StablecoinSupplyPanel>` already iterates the result
list keyed by `asset`; it auto-renders rows for new symbols.

## Operator setup

After the PR merges and deploys, the operator does ONE manual step:

1. Open the existing Dune query at `https://dune.com/queries/<DUNE_QUERY_ID_STABLECOIN_SUPPLY>`.
2. Replace the SQL body with the new `backend/dune/stablecoin_supply.sql`.
3. Click "Save."
4. The next `sync_dune_flows` worker run (within ~5 min by default) writes the new rows.

A line in CLAUDE.md documents this, similar to how the original Dune-setup steps are documented in `docs/dune-setup.md`.

No new env vars. No migrations. No FX-provider hookup.

## Edge cases

- **EUR/CHF rate drift.** A 10% drift in EUR→USD over a year would
  shift a EUROC threshold from $250k to ~$225k or ~$275k. Both still
  whale-sized; documented as acceptable. When operators see thresholds
  drifting visibly, refresh `price_usd_approx` in the registry — same
  refresh ritual already in place for volatile tokens.
- **A wrong contract address is wired.** Mitigation: the 6 addresses
  in this spec are verified against Etherscan tags + issuer
  documentation as of 2026-05-01. Spec freezes them; reviewers verify
  before merging.
- **Symbol collision.** No collisions in the new set. PYUSD, FDUSD,
  USDS, GHO, EUROC, ZCHF are all distinct from existing.
- **GHO transfers.** GHO has a unique mint pattern (Aave protocol),
  but transfer events look standard; no special handling needed.
- **USDS migration noise.** USDS is the rebrand of DAI's successor
  (Sky's Maker fork). DAI and USDS coexist; both are tracked. Some
  whale flows may show as "DAI → USDS" via Maker's converter — both
  legs persist as their own transfer events.

## Tests

Backend (pytest, testcontainers):
- New unit test in `tests/test_realtime_parser.py` — call
  `parse_erc20_log` with a synthetic EUROC transfer (1 unit = 6
  decimals, raw=`250_000_000_000` for 250k EUROC). Verify
  `usd_value == 250_000 * 1.08 = 270_000`, threshold compare
  uses USD not native, persisted symbol = `"EUROC"`.
- New unit test for ZCHF same shape.
- New unit test for PYUSD (USD-pegged path, sanity).
- Existing USDT/USDC/DAI tests should continue passing unchanged.
- New schema test: `WhaleAsset` validates `"PYUSD"` etc. and rejects
  `"WRONG"`.

Frontend: no automated tests (vitest not configured); validation =
`npm run build` + manual smoke (whale panel filter dropdown shows
new options; a real PYUSD/FDUSD whale transfer eventually appears
once the listener catches one).

## Implementation milestones

(Refined in the writing-plans pass.)

1. Add `StableToken` dataclass + new `STABLES` registry with all 9
   entries + new tests.
2. Update `parse_erc20_log` to use `stable.price_usd_approx` for both
   threshold compare and `usd_value`. Update the pending-tx parallel
   path same way. Existing tests continue passing.
3. Update `WhaleAsset` schema in backend (`schemas.py`) and frontend
   (`api.ts`).
4. Update `WhaleTransfersPanel` asset-filter dropdown options.
5. Update `backend/dune/stablecoin_supply.sql`.
6. CLAUDE.md note + manual smoke checklist.

## Risks and known limits

- **No backfill.** Whale transfers from before the listener picks up
  the new tokens won't appear retroactively. The Dune-driven
  stablecoin-supply panel does fill historically (Dune queries the
  blockchain directly).
- **Issuer-pause / migration risk.** PYUSD, USDS, GHO are issued by
  centralized issuers (Paxos for PYUSD, MakerDAO for USDS, Aave for
  GHO). They can pause or migrate contracts without notice. The
  registry is a hand-curated list — rebroken contract addresses
  surface as zero whale events; documented.
- **Decimals confusion.** A wrong `decimals` value silently produces
  whale events with absurd amounts (millions or billionths off). The
  6 new entries use values verified against Etherscan; any future
  add must verify the same.

## Future work (not v1)

- **The 5 deferred coins** (EURCV, EUROS, BRZ, XSGD, tGBP) once the
  client confirms specific contract addresses.
- **Live FX rates** via CoinGecko (with Redis cache), eliminating
  the periodic-refresh ritual on `price_usd_approx`.
- **Order-flow / volume-buckets coverage of stables** — currently
  WETH-only; expanding to per-stablecoin DEX volume is its own
  project.
- **Minute-resolution volume charts** — separate sub-feature, deferred
  per scope discussion.
