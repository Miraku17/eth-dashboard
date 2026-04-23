-- Net supply change (mints - burns) per stablecoin, 1h buckets, last 30d.
-- Result columns: ts_bucket, asset, direction, usd_value
with mints as (
  select
    date_trunc('hour', block_time) as ts_bucket,
    symbol as asset,
    'in' as direction,
    sum(amount_usd) as usd_value
  from tokens.transfers
  where blockchain = 'ethereum'
    and "from" = 0x0000000000000000000000000000000000000000
    and symbol in ('USDT','USDC','DAI')
    and block_time > now() - interval '30' day
    and amount_usd is not null
  group by 1, 2
),
burns as (
  select
    date_trunc('hour', block_time) as ts_bucket,
    symbol as asset,
    'out' as direction,
    sum(amount_usd) as usd_value
  from tokens.transfers
  where blockchain = 'ethereum'
    and to = 0x0000000000000000000000000000000000000000
    and symbol in ('USDT','USDC','DAI')
    and block_time > now() - interval '30' day
    and amount_usd is not null
  group by 1, 2
)
select * from mints
union all
select * from burns
order by ts_bucket desc
