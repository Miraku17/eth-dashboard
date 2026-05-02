-- Beacon-chain flow legs per hour, last 30d. Sourced from the curated
-- staking_ethereum.flows spell (one row per validator event, with
-- amount_staked / amount_partial_withdrawn / amount_full_withdrawn populated).
--
-- Result columns: ts_bucket, kind, amount_eth, amount_usd
-- kind ∈ {deposit, withdrawal_partial, withdrawal_full}
with hourly as (
  select
    date_trunc('hour', f.block_time) as ts_bucket,
    sum(f.amount_staked) as deposit_eth,
    sum(f.amount_partial_withdrawn) as partial_eth,
    sum(f.amount_full_withdrawn) as full_eth
  from staking_ethereum.flows f
  where f.block_time > now() - interval '30' day
  group by 1
),
eth_price as (
  select date_trunc('hour', minute) as ts_bucket, avg(price) as price_usd
  from prices.usd
  where blockchain = 'ethereum'
    and symbol = 'ETH'
    and minute > now() - interval '30' day
  group by 1
),
priced as (
  select
    h.ts_bucket,
    h.deposit_eth,
    h.partial_eth,
    h.full_eth,
    coalesce(p.price_usd, 0) as price_usd
  from hourly h
  left join eth_price p using (ts_bucket)
)
select ts_bucket, 'deposit' as kind,
       deposit_eth as amount_eth,
       deposit_eth * price_usd as amount_usd
from priced where deposit_eth > 0
union all
select ts_bucket, 'withdrawal_partial' as kind,
       partial_eth as amount_eth,
       partial_eth * price_usd as amount_usd
from priced where partial_eth > 0
union all
select ts_bucket, 'withdrawal_full' as kind,
       full_eth as amount_eth,
       full_eth * price_usd as amount_usd
from priced where full_eth > 0
order by ts_bucket desc
