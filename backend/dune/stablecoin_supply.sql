-- Net supply change (mints - burns) per stablecoin, 1h buckets, last 30d.
-- Filter by contract_address (Circle renamed EUROC→EURC in 2024 — symbol filter would miss it).
-- Output uses our app's preferred symbol via the asset_alias CTE.
--
-- USD pricing: Dune's tokens.transfers.amount_usd is null for most non-USDC/USDT
-- stables (FDUSD, ZCHF, EURCV, EURe, tGBP, etc. — Dune doesn't carry a price feed
-- for them). We self-price using a curated peg rate per asset, mirroring the
-- realtime parser's price_usd_approx. Result is "USD-anchored notional", same
-- semantics as the whale-transfer threshold path. Rates drift but ±10% is
-- harmless at this aggregation level; refresh occasionally.
--
-- Result columns: ts_bucket, asset, direction, usd_value
with asset_alias as (
  select * from (values
    (0xdac17f958d2ee523a2206206994597c13d831ec7, 'USDT',  1.00),
    (0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48, 'USDC',  1.00),
    (0x6b175474e89094c44da98b954eedeac495271d0f, 'DAI',   1.00),
    (0x6c3ea9036406852006290770bedfcaba0e23a0e8, 'PYUSD', 1.00),
    (0xc5f0f7b66764f6ec8c8dff7ba683102295e16409, 'FDUSD', 1.00),
    (0xdc035d45d973e3ec169d2276ddab16f1e407384f, 'USDS',  1.00),
    (0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f, 'GHO',   1.00),
    (0x1abaea1f7c830bd89acc67ec4af516284b1bc33c, 'EUROC', 1.08),
    (0xb58e61c3098d85632df34eecfb899a1ed80921cb, 'ZCHF',  1.10),
    (0x5f7827fdeb7c20b443265fc2f40845b715385ff2, 'EURCV', 1.08),
    (0x39b8b6385416f4ca36a20319f70d28621895279d, 'EURe',  1.08),
    (0x27f6c8289550fce67f6b50bed1f519966afe5287, 'tGBP',  1.27)
  ) as t(contract_address, asset, price_usd_approx)
),
mints as (
  select
    date_trunc('hour', t.block_time) as ts_bucket,
    a.asset,
    'in' as direction,
    sum(t.amount * a.price_usd_approx) as usd_value
  from tokens.transfers t
  join asset_alias a on a.contract_address = t.contract_address
  where t.blockchain = 'ethereum'
    and t."from" = 0x0000000000000000000000000000000000000000
    and t.block_time > now() - interval '30' day
  group by 1, 2
),
burns as (
  select
    date_trunc('hour', t.block_time) as ts_bucket,
    a.asset,
    'out' as direction,
    sum(t.amount * a.price_usd_approx) as usd_value
  from tokens.transfers t
  join asset_alias a on a.contract_address = t.contract_address
  where t.blockchain = 'ethereum'
    and t.to = 0x0000000000000000000000000000000000000000
    and t.block_time > now() - interval '30' day
  group by 1, 2
)
select * from mints
union all
select * from burns
order by ts_bucket desc
