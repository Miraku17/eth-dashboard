-- Exchange netflow per major CEX for ETH + top stables, 1h buckets, last 48h.
-- Result columns: ts_bucket, exchange, direction, asset, usd_value
with labeled as (
  select address, name as exchange
  from dune.defi.cex_evm_addresses
  where chain = 'ethereum'
    and name in ('Binance','Coinbase','Kraken','OKX','Bitfinex')
),
eth_flows as (
  select
    date_trunc('hour', block_time) as ts_bucket,
    case when to_addr.exchange is not null then to_addr.exchange else from_addr.exchange end as exchange,
    case when to_addr.exchange is not null then 'in' else 'out' end as direction,
    'ETH' as asset,
    sum(value_usd) as usd_value
  from ethereum.traces t
    left join labeled to_addr on to_addr.address = t.to
    left join labeled from_addr on from_addr.address = t."from"
  where t.success
    and (to_addr.exchange is not null or from_addr.exchange is not null)
    and t.block_time > now() - interval '48' hour
    and t.value > 0
    and t.tx_success
  group by 1,2,3
),
token_flows as (
  select
    date_trunc('hour', evt_block_time) as ts_bucket,
    case when to_addr.exchange is not null then to_addr.exchange else from_addr.exchange end as exchange,
    case when to_addr.exchange is not null then 'in' else 'out' end as direction,
    tokens.symbol as asset,
    sum(value_usd) as usd_value
  from erc20_ethereum.evt_Transfer t
    join tokens.erc20 tokens on tokens.contract_address = t.contract_address and tokens.blockchain = 'ethereum'
    left join labeled to_addr on to_addr.address = t.to
    left join labeled from_addr on from_addr.address = t."from"
  where (to_addr.exchange is not null or from_addr.exchange is not null)
    and tokens.symbol in ('USDT','USDC','DAI','WETH')
    and t.evt_block_time > now() - interval '48' hour
  group by 1,2,3,4
)
select * from eth_flows
union all
select * from token_flows
order by ts_bucket desc
