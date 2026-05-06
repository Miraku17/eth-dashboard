# Arbitrum Setup (v5 — GMX V2 perps)

The on-chain-perps panel reads its data from a sibling realtime listener
(`arbitrum_realtime`) that subscribes to the GMX V2 EventEmitter contract
on Arbitrum mainnet. This page covers the operator setup.

## Endpoints

You need **two** Arbitrum endpoints (a WebSocket for log subscriptions and
an HTTP for tx-receipt lookups):

```
ARBITRUM_WS_URL=
ARBITRUM_HTTP_URL=
```

### Option A — Reuse your Alchemy key (recommended)

Alchemy serves Arbitrum mainnet on the same key/plan that the project's
mainnet listener already uses. **No new account required.** If
`ALCHEMY_API_KEY` is set in `.env` and `ARBITRUM_WS_URL` is unset, the
listener falls back to:

```
wss://arb-mainnet.g.alchemy.com/v2/<ALCHEMY_API_KEY>
https://arb-mainnet.g.alchemy.com/v2/<ALCHEMY_API_KEY>
```

In this case you can leave both `ARBITRUM_WS_URL` and `ARBITRUM_HTTP_URL`
blank — the fallback handles it. Free tier limit (300 CUs/sec) is well
above what `eth_getLogs` for the GMX EventEmitter emits at peak load
(typically <1 event/second).

### Option B — Self-hosted Arbitrum Nitro

Point at your own Nitro node:

```
ARBITRUM_WS_URL=ws://172.17.0.1:8547
ARBITRUM_HTTP_URL=http://172.17.0.1:8546
```

(Default Nitro ports; adjust if you've reconfigured.)

### Option C — Other RPC providers

Any provider that supports `eth_subscribe newHeads` and `eth_getLogs` on
Arbitrum mainnet works. Tested: Alchemy. Should work without changes:
QuickNode, Infura, Ankr (free tier rate limits may surface during heavy
GMX activity — escalate to paid if you see drops in the panel).

## After setting endpoints

```bash
docker compose up -d arbitrum_realtime
docker compose logs -f arbitrum_realtime
```

You should see `subscribed to arbitrum newHeads` within seconds. The
first `block=… gmx_events=N` log line confirms the decoder is picking up
real GMX events. Initial readings are **forward-only** — the panel
populates as new positions/liquidations occur. There is no historical
backfill in v1.

## Idle mode

If neither `ARBITRUM_WS_URL` nor `ALCHEMY_API_KEY` is set, the listener
container starts in idle mode (logs a warning, sleeps) so the rest of
the stack still boots cleanly during local dev. The panel will simply
display "no events in the last 24h" until endpoints are configured.

## What it tracks

The listener subscribes to **PositionIncrease** and **PositionDecrease**
events from `0xC8ee91A54287DB53897056e12D9819156D3822Fb` (the GMX V2
EventEmitter). Eight markets are recognised in v1: ETH-USD, BTC-USD,
SOL-USD, AVAX-USD, ARB-USD, LINK-USD, DOGE-USD, NEAR-USD. Other markets
appear in the EventEmitter feed but are dropped at decode time (see
`backend/app/realtime/gmx_v2_markets.py` to extend).
