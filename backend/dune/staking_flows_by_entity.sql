-- Beacon-chain flows broken down per issuer entity.
-- Same source as backend/dune/staking_flows.sql (the curated
-- staking_ethereum.flows spell) but grouped additionally by entity
-- so the panel can show "who is depositing / exiting".
--
-- Long tail: most rows in the spell tag a per-validator "entity" that's
-- the validator owner's ENS name (one validator stakers). We fold any
-- entity that doesn't accumulate at least 100 ETH / 30d into a single
-- bucket called 'Solo stakers' so the panel doesn't drown in 1-validator
-- ENS names. NULL entities (Dune couldn't attribute) collapse into
-- 'Unattributed'.
--
-- Result columns: ts_bucket, kind, entity, amount_eth, amount_usd
-- kind ∈ {deposit, withdrawal_partial, withdrawal_full}
-- entity ∈ {<top issuer name>, 'Solo stakers', 'Unattributed'}
with hourly as (
  select
    date_trunc('hour', f.block_time) as ts_bucket,
    coalesce(f.entity, 'Unattributed') as raw_entity,
    sum(f.amount_staked) as deposit_eth,
    sum(f.amount_partial_withdrawn) as partial_eth,
    sum(f.amount_full_withdrawn) as full_eth
  from staking_ethereum.flows f
  where f.block_time > now() - interval '30' day
  group by 1, 2
),
totals_30d as (
  select raw_entity,
         sum(deposit_eth) + sum(full_eth) as activity
  from hourly
  group by 1
),
named as (
  -- Entities with meaningful 30d activity (>= 100 ETH combined deposit + exit)
  -- get their own row; everything else folds into 'Solo stakers'.
  select t.raw_entity,
         case
           when t.raw_entity = 'Unattributed' then 'Unattributed'
           when t.activity >= 100 then t.raw_entity
           else 'Solo stakers'
         end as entity
  from totals_30d t
),
hourly_named as (
  select h.ts_bucket,
         n.entity,
         h.deposit_eth,
         h.partial_eth,
         h.full_eth
  from hourly h
  join named n on n.raw_entity = h.raw_entity
),
agg as (
  select ts_bucket, entity,
         sum(deposit_eth) as deposit_eth,
         sum(partial_eth) as partial_eth,
         sum(full_eth) as full_eth
  from hourly_named
  group by 1, 2
),
eth_price as (
  -- Native ETH (blockchain=null, contract_address=null in prices.usd)
  select date_trunc('hour', minute) as ts_bucket, avg(price) as price_usd
  from prices.usd
  where symbol = 'ETH'
    and blockchain is null
    and contract_address is null
    and minute > now() - interval '30' day
  group by 1
),
priced as (
  select a.*, coalesce(p.price_usd, 0) as price_usd
  from agg a
  left join eth_price p on a.ts_bucket = p.ts_bucket
)
select ts_bucket, 'deposit' as kind, entity,
       deposit_eth as amount_eth,
       deposit_eth * price_usd as amount_usd
from priced where deposit_eth > 0
union all
select ts_bucket, 'withdrawal_partial' as kind, entity,
       partial_eth as amount_eth,
       partial_eth * price_usd as amount_usd
from priced where partial_eth > 0
union all
select ts_bucket, 'withdrawal_full' as kind, entity,
       full_eth as amount_eth,
       full_eth * price_usd as amount_usd
from priced where full_eth > 0
order by ts_bucket desc
