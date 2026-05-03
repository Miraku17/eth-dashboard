-- Hourly on-chain buy vs sell pressure for ETH on major DEXes,
-- broken out per-DEX so the panel can stack the contribution from
-- Uniswap V2/V3, Curve, Balancer, and "other" venues separately.
-- Uses Dune's curated `dex.trades` table which unifies Uniswap v2/v3,
-- Curve, Balancer, SushiSwap, Pancakeswap, etc. WETH is the canonical
-- wrapped-ETH address on mainnet — all ETH DEX trades settle through it.
--
-- Semantics:
--   side='buy'  → someone bought WETH (bullish pressure)
--   side='sell' → someone sold WETH   (bearish pressure)
--
-- The `dex` column normalizes Dune's (project, version) into a small
-- fixed vocabulary so the panel legend doesn't explode. Top 4 named
-- venues account for >95% of WETH DEX volume; the long tail rolls
-- into 'other'.
--
-- Result columns: ts_bucket, dex, side, usd_value, trade_count

WITH classified AS (
  SELECT
    date_trunc('hour', block_time) AS ts_bucket,
    CASE
      WHEN project = 'uniswap'  AND version = '2' THEN 'uniswap_v2'
      WHEN project = 'uniswap'  AND version = '3' THEN 'uniswap_v3'
      WHEN project = 'curve'                       THEN 'curve'
      WHEN project = 'balancer'                    THEN 'balancer'
      ELSE 'other'
    END AS dex,
    CASE
      WHEN token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 THEN 'buy'
      WHEN token_sold_address   = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 THEN 'sell'
    END AS side,
    amount_usd
  FROM dex.trades
  WHERE blockchain = 'ethereum'
    -- Partition pruning: filter by block_date so DuneSQL skips irrelevant daily partitions.
    AND block_date >= current_date - interval '7' day
    AND block_time > now() - interval '7' day
    AND (
      token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
      OR token_sold_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
    )
    AND amount_usd IS NOT NULL
    AND amount_usd > 0
)
SELECT
  ts_bucket,
  dex,
  side,
  sum(amount_usd) AS usd_value,
  count(*) AS trade_count
FROM classified
WHERE side IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY ts_bucket DESC, dex, side
