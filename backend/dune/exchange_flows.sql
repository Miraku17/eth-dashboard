-- Exchange netflow per major CEX for ETH + top stables, 1h buckets, last 30d.
-- Result columns: ts_bucket, exchange, direction, asset, usd_value
select
  date_trunc('hour', block_time) as ts_bucket,
  cex_name as exchange,
  case
    when lower(flow_type) like '%inflow%' then 'in'
    when lower(flow_type) like '%outflow%' then 'out'
    else 'out'
  end as direction,
  token_symbol as asset,
  sum(amount_usd) as usd_value
from cex.flows
where blockchain = 'ethereum'
  and token_symbol in ('ETH','USDT','USDC','DAI','WETH')
  and cex_name in ('Binance','Coinbase','Kraken','OKX','Bitfinex')
  and block_time > now() - interval '30' day
  and amount_usd is not null
  and flow_type in ('Inflow','Outflow')
group by 1, 2, 3, 4
order by ts_bucket desc
