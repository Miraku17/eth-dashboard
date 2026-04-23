-- Net supply change (mints - burns) per stablecoin, 1h buckets, last 48h.
-- Result columns: ts_bucket, asset, direction, usd_value
with mints as (
  select
    date_trunc('hour', evt_block_time) as ts_bucket,
    tokens.symbol as asset,
    'in' as direction,
    sum(value_usd) as usd_value
  from erc20_ethereum.evt_Transfer t
    join tokens.erc20 tokens on tokens.contract_address = t.contract_address and tokens.blockchain = 'ethereum'
  where t."from" = 0x0000000000000000000000000000000000000000
    and tokens.symbol in ('USDT','USDC','DAI')
    and t.evt_block_time > now() - interval '48' hour
  group by 1,2
),
burns as (
  select
    date_trunc('hour', evt_block_time) as ts_bucket,
    tokens.symbol as asset,
    'out' as direction,
    sum(value_usd) as usd_value
  from erc20_ethereum.evt_Transfer t
    join tokens.erc20 tokens on tokens.contract_address = t.contract_address and tokens.blockchain = 'ethereum'
  where t.to = 0x0000000000000000000000000000000000000000
    and tokens.symbol in ('USDT','USDC','DAI')
    and t.evt_block_time > now() - interval '48' hour
  group by 1,2
)
select * from mints
union all
select * from burns
order by ts_bucket desc
