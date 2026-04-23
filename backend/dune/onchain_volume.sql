-- Daily USD tx volume broken down by asset, last 30 days.
-- Result columns: ts_bucket, asset, tx_count, usd_value
with eth_volume as (
  select
    date_trunc('day', block_time) as ts_bucket,
    'ETH' as asset,
    count(*) as tx_count,
    sum(value_usd) as usd_value
  from ethereum.traces
  where block_time > now() - interval '30' day
    and success
    and value > 0
    and call_type = 'call'
  group by 1
),
token_volume as (
  select
    date_trunc('day', evt_block_time) as ts_bucket,
    tokens.symbol as asset,
    count(*) as tx_count,
    sum(value_usd) as usd_value
  from erc20_ethereum.evt_Transfer t
    join tokens.erc20 tokens on tokens.contract_address = t.contract_address and tokens.blockchain = 'ethereum'
  where tokens.symbol in ('USDT','USDC','DAI','WETH')
    and t.evt_block_time > now() - interval '30' day
  group by 1,2
)
select * from eth_volume
union all
select * from token_volume
order by ts_bucket desc, asset
