# Dune Setup

This project reads 3 queries from Dune Analytics. You need to save them to your Dune account once, then paste the IDs into `.env`.

## Steps

1. Sign in at https://dune.com and go to https://dune.com/queries
2. Click **New Query** → **Spellbook (DuneSQL)** engine
3. For each file under `backend/dune/*.sql`:
   - Paste the SQL into the editor
   - Click **Run** once to verify it executes
   - Click **Save** → give it a name (e.g. "etherscope exchange flows")
   - The URL now reads `https://dune.com/queries/<QUERY_ID>/…` — copy the numeric ID
4. Paste the three IDs into `.env`:

   ```
   DUNE_QUERY_ID_EXCHANGE_FLOWS=<id from exchange_flows.sql>
   DUNE_QUERY_ID_STABLECOIN_SUPPLY=<id from stablecoin_supply.sql>
   DUNE_QUERY_ID_ONCHAIN_VOLUME=<id from onchain_volume.sql>
   ```

5. Restart the worker: `docker compose restart worker`

The worker will then begin syncing every `DUNE_SYNC_INTERVAL_MIN` minutes (default 240 = 4 hours).

## Execution quota

Free tier is ~500 executions/month. 3 queries × once per 240 minutes × 30 days ≈ 540/month — right at the limit. Tune `DUNE_SYNC_INTERVAL_MIN` up if you hit the cap, or upgrade to the $49/month Analyst plan (25k executions).
