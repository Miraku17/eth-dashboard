-- Hourly ETH (WETH) DEX volume bucketed by trade size (USD).
-- Lets the dashboard show whether moves are retail- or whale-driven by
-- breaking total volume into four notional bands.
--
-- Buckets:
--   retail : trade USD < 10k
--   mid    : 10k  ≤ trade USD < 100k
--   large  : 100k ≤ trade USD < 1M
--   whale  : trade USD ≥ 1M
--
-- Same source as order_flow (`dex.trades` filtered to WETH on Ethereum)
-- so credit usage stays predictable. Schedule: every 8h via the worker
-- cron, mirroring DUNE_ORDER_FLOW_INTERVAL_MIN by default.
--
-- Result columns: ts_bucket, bucket, usd_value, trade_count

WITH classified AS (
  SELECT
    date_trunc('hour', block_time) AS ts_bucket,
    CASE
      WHEN amount_usd < 10000   THEN 'retail'
      WHEN amount_usd < 100000  THEN 'mid'
      WHEN amount_usd < 1000000 THEN 'large'
      ELSE 'whale'
    END AS bucket,
    amount_usd
  FROM dex.trades
  WHERE blockchain = 'ethereum'
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
  bucket,
  sum(amount_usd) AS usd_value,
  count(*) AS trade_count
FROM classified
GROUP BY 1, 2
ORDER BY ts_bucket DESC, bucket
