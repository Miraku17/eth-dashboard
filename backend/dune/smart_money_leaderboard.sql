-- Smart-money leaderboard per-wallet aggregate feed (v2).
-- Returns one row per wallet with 30d WETH trade totals for the top 500
-- wallets by volume on Ethereum mainnet DEXes.
--
-- WHY AGGREGATES, NOT PER-TRADE ROWS:
-- The per-trade shape (tens of thousands of rows) blows through the Dune
-- free-tier `/results` datapoint budget. Aggregating in SQL keeps the
-- payload at ~500 rows. PnL is computed in the backend as:
--   realized ≈ min(weth_bought, weth_sold) × (avg_sell_price − avg_buy_price)
-- which is exact for fully-closed round-trips and directionally correct for
-- flippers. It deviates from true FIFO for partial closes on large positions.
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
windowed AS (
  SELECT
    tx_from AS trader,
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
    AND block_date >= current_date - interval '30' day
    AND block_time > now() - interval '30' day
    AND (
      token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
      OR token_sold_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
    )
    AND amount_usd IS NOT NULL
    AND amount_usd > 0
    -- Plausibility caps: filter out rows where Dune's token_*_amount is
    -- in raw wei instead of decimal form (a known data-quality issue on
    -- some pools). No real DEX trade exceeds ~100k WETH or $100M per tx.
    AND amount_usd < 100000000
    AND (
      CASE
        WHEN token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 THEN token_bought_amount
        ELSE token_sold_amount
      END
    ) < 100000
    AND tx_from NOT IN (SELECT address FROM router_exclusions)
),
per_wallet AS (
  SELECT
    trader,
    SUM(CASE WHEN side = 'buy'  THEN weth_amount ELSE 0 END) AS weth_bought,
    SUM(CASE WHEN side = 'sell' THEN weth_amount ELSE 0 END) AS weth_sold,
    SUM(CASE WHEN side = 'buy'  THEN amount_usd  ELSE 0 END) AS usd_spent,
    SUM(CASE WHEN side = 'sell' THEN amount_usd  ELSE 0 END) AS usd_received,
    SUM(amount_usd) AS total_volume,
    COUNT(*) AS trade_count
  FROM windowed
  GROUP BY trader
),
wallet_labels AS (
  -- Pre-aggregate so a trader with multiple label rows doesn't fan out.
  SELECT address, MAX(name) AS name
  FROM labels.addresses
  WHERE blockchain = 'ethereum'
  GROUP BY address
)
SELECT
  CAST(w.trader AS VARCHAR)         AS trader,
  CAST(w.weth_bought AS VARCHAR)    AS weth_bought,
  CAST(w.weth_sold AS VARCHAR)      AS weth_sold,
  CAST(w.usd_spent AS VARCHAR)      AS usd_spent,
  CAST(w.usd_received AS VARCHAR)   AS usd_received,
  w.trade_count,
  l.name                            AS label
FROM per_wallet w
LEFT JOIN wallet_labels l ON l.address = w.trader
ORDER BY w.total_volume DESC
LIMIT 500;
