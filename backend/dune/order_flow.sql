-- Hourly on-chain buy vs sell pressure for ETH on major DEXes.
-- Uses Dune's curated `dex.trades` table which unifies Uniswap v2/v3, Curve,
-- Balancer, SushiSwap, Pancakeswap, etc. WETH is the canonical wrapped-ETH
-- address on mainnet — all ETH DEX trades settle through WETH.
--
-- Semantics:
--   side='buy'  → someone bought WETH (bullish pressure)
--   side='sell' → someone sold WETH   (bearish pressure)
--
-- Result columns: ts_bucket, side, usd_value, trade_count

WITH weth AS (
  SELECT 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 AS addr
)
SELECT
  date_trunc('hour', block_time) AS ts_bucket,
  CASE
    WHEN token_bought_address = (SELECT addr FROM weth) THEN 'buy'
    WHEN token_sold_address   = (SELECT addr FROM weth) THEN 'sell'
  END AS side,
  sum(amount_usd) AS usd_value,
  count(*) AS trade_count
FROM dex.trades
WHERE blockchain = 'ethereum'
  AND block_time > now() - interval '7' day
  AND (
    token_bought_address = (SELECT addr FROM weth)
    OR token_sold_address = (SELECT addr FROM weth)
  )
  AND amount_usd IS NOT NULL
  AND amount_usd > 0
GROUP BY 1, 2
HAVING side IS NOT NULL
ORDER BY ts_bucket DESC, side
