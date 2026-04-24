# Dune Setup

This project reads **4 queries** from Dune Analytics. You need to save them to
your Dune account once, then paste the IDs into `.env`.

## Steps

1. Sign in at https://dune.com and go to https://dune.com/queries
2. Click **New Query** → **Spellbook (DuneSQL)** engine
3. For each file under `backend/dune/*.sql`:
   - Paste the SQL into the editor
   - Click **Run** once to verify it executes
   - Click **Save** → give it a name (e.g. "etherscope exchange flows")
   - The URL now reads `https://dune.com/queries/<QUERY_ID>/…` — copy the numeric ID
4. Paste the IDs into `.env`:

   ```
   DUNE_QUERY_ID_EXCHANGE_FLOWS=<id from exchange_flows.sql>
   DUNE_QUERY_ID_STABLECOIN_SUPPLY=<id from stablecoin_supply.sql>
   DUNE_QUERY_ID_ONCHAIN_VOLUME=<id from onchain_volume.sql>
   DUNE_QUERY_ID_ORDER_FLOW=<id from order_flow.sql>
   ```

5. Restart the worker: `docker compose restart worker`

The worker will then begin syncing:
- `exchange_flows`, `stablecoin_supply`, `onchain_volume` every
  `DUNE_SYNC_INTERVAL_MIN` minutes (default 240 = 4h)
- `order_flow` every `DUNE_ORDER_FLOW_INTERVAL_MIN` minutes (default 480 = 8h)

## Execution quota

Dune free tier is ~2,500 credits/month ≈ 250 medium-engine executions.

Default cadence per query:
- 3 main flow queries × every 4h = 18/day × 30 = **540/month** (over budget)
- 1 order-flow query × every 8h = 3/day × 30 = **90/month**

If you hit the cap, tune `DUNE_SYNC_INTERVAL_MIN` up to **360** (6h) —
brings total to ~450/month — or pay for a higher tier.
