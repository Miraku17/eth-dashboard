-- Smart-money leaderboard candidate feed (v2).
-- Returns raw WETH trade rows for the top 500 wallets by 30d WETH volume on
-- Ethereum mainnet DEXes. The backend reconstructs per-wallet FIFO realized
-- PnL from these rows.
--
-- Semantics:
--   side='buy'  → wallet bought WETH (spent something for ETH exposure)
--   side='sell' → wallet sold WETH  (closed out ETH exposure)
--   weth_amount is the WETH leg of the trade; amount_usd is Dune's USD tag.
--
-- Router/aggregator EOAs are excluded so the leaderboard surfaces
-- end-user wallets rather than 1inch, KyberSwap, etc.

WITH router_exclusions (address) AS (
  VALUES
    (0x1111111254EEB25477B68fb85Ed929f73A960582),  -- 1inch v5 router
    (0x6131B5fae19EA4f9D964eAc0408E4408b66337b5),  -- KyberSwap MetaAggregator
    (0xdef1c0ded9bec7f1a1670819833240f027b25eff),  -- 0x Exchange Proxy
    (0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45),  -- Uniswap Universal Router
    (0xE592427A0AEce92De3Edee1F18E0157C05861564),  -- Uniswap V3 SwapRouter
    (0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD),  -- Uniswap Universal Router v1_2
    (0x9008D19f58AAbD9eD0D60971565AA8510560ab41)   -- CoW Protocol GPv2Settlement
),
windowed_trades AS (
  SELECT
    tx_from AS trader,
    block_time,
    CASE
      WHEN token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 THEN 'buy'
      ELSE 'sell'
    END AS side,
    CASE
      WHEN token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 THEN token_bought_amount
      ELSE token_sold_amount
    END AS weth_amount,
    amount_usd
  FROM dex.trades
  WHERE blockchain = 'ethereum'
    -- Partition pruning: both date and timestamp predicates so DuneSQL skips
    -- irrelevant daily partitions AND bounds the rolling window to 30d.
    AND block_date >= current_date - interval '30' day
    AND block_time > now() - interval '30' day
    AND (
      token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
      OR token_sold_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
    )
    AND amount_usd IS NOT NULL
    AND amount_usd > 0
    AND tx_from NOT IN (SELECT address FROM router_exclusions)
),
candidates AS (
  SELECT trader
  FROM windowed_trades
  GROUP BY trader
  ORDER BY SUM(amount_usd) DESC
  LIMIT 500
)
SELECT
  CAST(t.trader AS VARCHAR) AS trader,
  t.block_time,
  t.side,
  CAST(t.weth_amount AS VARCHAR) AS weth_amount,
  CAST(t.amount_usd AS VARCHAR) AS amount_usd,
  l.name AS label
FROM windowed_trades t
JOIN candidates c USING (trader)
LEFT JOIN labels.addresses l
  ON l.address = t.trader AND l.blockchain = 'ethereum'
ORDER BY t.trader, t.block_time;


