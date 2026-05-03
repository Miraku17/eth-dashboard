-- L1 ↔ L2 bridge flows per (hour, bridge, direction, asset).
--
-- Tracks the canonical L1 bridge contracts for the four largest L2s by
-- mainnet TVL: Arbitrum, Base, Optimism, zkSync Era. Direction:
--   "in"  = deposit  (someone TRANSFERS TO the bridge → funds leave for L2)
--   "out" = withdraw (bridge TRANSFERS OUT to a user → funds return to L1)
--
-- Self-prices via prices.usd for ERC-20s. Native ETH transfers come
-- through tokens.transfers with symbol='ETH' and amount_usd populated by
-- the canonical price feed.
--
-- Result columns: ts_bucket, bridge, direction, asset, usd_value
with bridge_addrs as (
  select * from (values
    -- Arbitrum One: Inbox + L1ERC20Gateway
    (0x4dbd4fc535ac27206064b68ffcf827b0a60bab3f, 'arbitrum'),
    (0x72ce9c846789fdb6fc1f34ac4ad25dd9ef7031ef, 'arbitrum'),
    (0xa10c7ce4b876998858b1a9e12b10092229c40a0a, 'arbitrum'),
    -- Base: OptimismPortal + L1ERC20Bridge
    (0x49048044d57e1c92a77f79988d21fa8faf74e97e, 'base'),
    (0x3154cf16ccdb4c6d922629664174b904d80f2c35, 'base'),
    -- Optimism: OptimismPortal + L1StandardBridgeProxy
    (0xbeb5fc579115071764c7423a4f12edde41f106ed, 'optimism'),
    (0x99c9fc46f92e8a1c0dec1b1747d010903e884be1, 'optimism'),
    -- zkSync Era: Diamond proxy + L1ERC20Bridge
    (0x32400084c286cf3e17e7b677ea9583e60a000324, 'zksync'),
    (0x57891966931eb4bb6fb81430e6ce0a03aabde063, 'zksync')
  ) as t(address, bridge)
),
deposits as (
  -- Funds flowing INTO the bridge contract on L1 → about to be replicated on L2.
  select
    date_trunc('hour', t.block_time) as ts_bucket,
    b.bridge,
    'in' as direction,
    coalesce(t.symbol, 'OTHER') as asset,
    sum(t.amount_usd) as usd_value
  from tokens.transfers t
  join bridge_addrs b on b."address" = t."to"
  where t.blockchain = 'ethereum'
    and t.block_time > now() - interval '30' day
    and t.amount_usd is not null
  group by 1, 2, 3, 4
),
withdrawals as (
  -- Bridge contract sending tokens to a user on L1 → withdrawal from L2.
  select
    date_trunc('hour', t.block_time) as ts_bucket,
    b.bridge,
    'out' as direction,
    coalesce(t.symbol, 'OTHER') as asset,
    sum(t.amount_usd) as usd_value
  from tokens.transfers t
  join bridge_addrs b on b."address" = t."from"
  where t.blockchain = 'ethereum'
    and t.block_time > now() - interval '30' day
    and t.amount_usd is not null
  group by 1, 2, 3, 4
)
select * from deposits
union all
select * from withdrawals
order by ts_bucket desc
