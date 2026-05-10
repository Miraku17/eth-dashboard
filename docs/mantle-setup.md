# Mantle realtime listener — operator setup

The Mantle DEX flow panel reads its data from a sibling realtime listener
(`mantle_realtime`) that subscribes to Agni V3 swap events on Mantle mainnet.
This page covers the operator setup.

## Prerequisites

- Postgres + Redis containers running (`make up`)
- Migrations applied (at minimum revision `0026`)

## Pick a Mantle WS endpoint

Public Mantle RPCs that expose `eth_subscribe` over WSS:

| Provider           | URL                                       | Notes                   |
|--------------------|-------------------------------------------|-------------------------|
| PublicNode         | `wss://mantle-rpc.publicnode.com`         | Free, no signup         |
| Ankr (free tier)   | `wss://rpc.ankr.com/mantle/ws`            | Free, occasional limits |
| Mantle official    | `wss://mantle-mainnet.public.blastapi.io` | Free                    |

Any of these works. The listener has a 60-second head-stall watchdog that
force-reconnects if the subscription goes silent, so occasional flakiness from
public endpoints is tolerable.

## Configure `.env`

```bash
MANTLE_WS_URL=wss://mantle-rpc.publicnode.com
```

When unset, the panel renders an empty-state message and the container idles.

## Bring up the container

```bash
docker compose --profile mantle up -d mantle_realtime
docker compose logs -f mantle_realtime
```

Expected first log lines:

```
mantle_realtime  INFO  mantle_realtime  mantle_realtime connected; pools=5
mantle_realtime  INFO  mantle_realtime  ...
```

If you see:

```
mantle_realtime  INFO  mantle_realtime  MANTLE_WS_URL unset; mantle_realtime idle
```

…your env var didn't propagate. Recheck `.env` and ensure `.env` is in the
working directory when you run the compose command.

## Verify data is flowing

After ~5 minutes of Mantle DEX swap activity, check the database:

```bash
docker compose exec postgres psql -U eth -d eth -c "SELECT * FROM mantle_order_flow ORDER BY ts_bucket DESC LIMIT 5;"
```

Rows appear once the first hour rolls over. The dashboard panel "Mantle order
flow" (Markets page) will populate within 60 seconds of the first hourly flush.

## Stopping

```bash
docker compose --profile mantle stop mantle_realtime
```

Mainnet and Arbitrum listeners are unaffected.

## Troubleshooting

- **Empty panel after 10+ minutes:** Check the container logs for connection
  errors. Public RPCs sometimes block requests from datacenter IPs.
- **Bar values show null:** CoinGecko is rate-limited or unreachable from the
  API container. The panel falls back to MNT-denominated bars; no data is lost.
- **Bars look wrong:** Confirm the pool addresses in
  `backend/app/realtime/mantle_dex_registry.py` are still Agni's top-5 by
  volume. Pool rankings rotate and may require periodic updates.
