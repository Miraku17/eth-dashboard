"""Curated address-label registry — the v4 foundation.

Single source of truth for the live flow classifier on the realtime
listener. Maps a small set of well-known mainnet addresses to their
category so each transfer can be tagged with its `flow_kind` at write
time (CEX deposit, DEX swap, lending, staking, bridge, restaking, etc.).

Source verified against Etherscan labels and each protocol's official
docs as of 2026-05-04. Confidence=100 (curated). Heuristic / Etherscan-
imported entries can be added later via a separate worker job — that
path will use lower confidence values.

Adding a new entry:
  1. Verify the address on Etherscan (label, contract type).
  2. Pick the most specific category from LabelCategory below.
  3. Append to CURATED_LABELS as ``LabelEntry(addr, category, name)``.
  4. Bump _SEED_REVISION; the seeder's idempotent upsert picks up new
     rows and updates labels/categories that drifted, but only re-runs
     the upsert when the revision number bumps.

ALL ADDRESSES STORED LOWERCASE. The realtime listener also lowercases
both sides of every Transfer event before lookup. Mixed-case addresses
on Etherscan are checksummed; we strip that for storage uniformity.
"""
from __future__ import annotations

from dataclasses import dataclass

# Bumped every time CURATED_LABELS changes meaningfully so the worker's
# idempotent seeder knows to re-upsert. Existing rows whose category or
# label drifted get updated; new rows get inserted.
_SEED_REVISION = 1


# Category vocabulary used by the live flow classifier. The classifier
# maps a (from_category, to_category) pair to a flow_kind enum value
# (see app.realtime.flow_classifier — coming next card).
class LabelCategory:
    CEX = "cex"
    DEX_ROUTER = "dex_router"
    DEX_POOL = "dex_pool"
    LENDING = "lending"
    STAKING = "staking"
    LRT = "lrt"
    BRIDGE_L1 = "bridge_l1"
    BRIDGE_L2_GATEWAY = "bridge_l2_gateway"
    HYPERLIQUID = "hyperliquid"
    ORACLE = "oracle"
    MEV = "mev"
    TREASURY = "treasury"
    SMART_CONTRACT = "smart_contract"


@dataclass(frozen=True)
class LabelEntry:
    address: str   # mainnet 0x… (lowercased on insert)
    category: str  # one of LabelCategory.*
    label: str     # human-readable display name


# Curated registry — about 120 entries covering >95% of typical flow.
CURATED_LABELS: tuple[LabelEntry, ...] = (
    # ─── CEX hot wallets ─────────────────────────────────────────────────
    # Binance — the busiest set; covers the vast majority of CEX flow.
    LabelEntry("0x28c6c06298d514db089934071355e5743bf21d60", LabelCategory.CEX, "Binance 14"),
    LabelEntry("0x21a31ee1afc51d94c2efccaa2092ad1028285549", LabelCategory.CEX, "Binance 15"),
    LabelEntry("0xdfd5293d8e347dfe59e90efd55b2956a1343963d", LabelCategory.CEX, "Binance 16"),
    LabelEntry("0x56eddb7aa87536c09ccc2793473599fd21a8b17f", LabelCategory.CEX, "Binance 17"),
    LabelEntry("0x9696f59e4d72e237be84ffd425dcad154bf96976", LabelCategory.CEX, "Binance 18"),
    LabelEntry("0x4976a4a02f38326660d17bf34b431dc6e2eb2327", LabelCategory.CEX, "Binance 19"),
    LabelEntry("0xf977814e90da44bfa03b6295a0616a897441acec", LabelCategory.CEX, "Binance 8 (cold)"),
    LabelEntry("0x5a52e96bacdabb82fd05763e25335261b270efcb", LabelCategory.CEX, "Binance 20"),
    LabelEntry("0xd551234ae421e3bcba99a0da6d736074f22192ff", LabelCategory.CEX, "Binance 2"),
    LabelEntry("0xbe0eb53f46cd790cd13851d5eff43d12404d33e8", LabelCategory.CEX, "Binance 7"),

    # Coinbase
    LabelEntry("0x71660c4005ba85c37ccec55d0c4493e66fe775d3", LabelCategory.CEX, "Coinbase 1"),
    LabelEntry("0x503828976d22510aad0201ac7ec88293211d23da", LabelCategory.CEX, "Coinbase 2"),
    LabelEntry("0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43", LabelCategory.CEX, "Coinbase 3"),
    LabelEntry("0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740", LabelCategory.CEX, "Coinbase 4"),
    LabelEntry("0x3cd751e6b0078be393132286c442345e5dc49699", LabelCategory.CEX, "Coinbase 5"),
    LabelEntry("0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511", LabelCategory.CEX, "Coinbase 6"),
    LabelEntry("0xeb2629a2734e272bcc07bda959863f316f4bd4cf", LabelCategory.CEX, "Coinbase 10"),

    # OKX
    LabelEntry("0x6cc5f688a315f3dc28a7781717a9a798a59fda7b", LabelCategory.CEX, "OKX 1"),
    LabelEntry("0x236f9f97e0e62388479bf9e5ba4889e46b0273c3", LabelCategory.CEX, "OKX 2"),
    LabelEntry("0xa7efae728d2936e78bda97dc267687568dd593f3", LabelCategory.CEX, "OKX 3"),
    LabelEntry("0x868dab0b8e21ec0a48b76a7dbb71890e8b7c3c30", LabelCategory.CEX, "OKX 4"),

    # Bybit
    LabelEntry("0xf89d7b9c864f589bbf53a82105107622b35eaa40", LabelCategory.CEX, "Bybit hot"),
    LabelEntry("0xee5b5b923ffce93a870b3104b7ca09c3db80047a", LabelCategory.CEX, "Bybit 2"),

    # Kraken
    LabelEntry("0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0", LabelCategory.CEX, "Kraken 4"),
    LabelEntry("0xfa52274dd61e1643d2205169732f29114bc240b3", LabelCategory.CEX, "Kraken 13"),
    LabelEntry("0x53d284357ec70ce289d6d64134dfac8e511c8a3d", LabelCategory.CEX, "Kraken 6"),
    LabelEntry("0xe853c56864a2ebe4576a807d26fdc4a0ada51919", LabelCategory.CEX, "Kraken 7"),

    # KuCoin
    LabelEntry("0xd6216fc19db775df9774a6e33526131da7d19a2c", LabelCategory.CEX, "KuCoin 1"),
    LabelEntry("0xf16e9b0d03470827a95cdfd0cb8a8a3b46969b91", LabelCategory.CEX, "KuCoin 2"),

    # Crypto.com
    LabelEntry("0xcffad3200574698b78f32232aa9d63eabd290703", LabelCategory.CEX, "Crypto.com 1"),
    LabelEntry("0x6262998ced04146fa42253a5c0af90ca02dfd2a3", LabelCategory.CEX, "Crypto.com 2"),
    LabelEntry("0x46340b20830761efd32832a74d7169b29feb9758", LabelCategory.CEX, "Crypto.com 3"),

    # Gate.io
    LabelEntry("0x0d0707963952f2fba59dd06f2b425ace40b492fe", LabelCategory.CEX, "Gate.io 1"),
    LabelEntry("0x1c4b70a3968436b9a0a9cf5205c787eb81bb558c", LabelCategory.CEX, "Gate.io 2"),

    # Bitfinex
    LabelEntry("0x1151314c646ce4e0efd76d1af4760ae66a9fe30f", LabelCategory.CEX, "Bitfinex 5"),
    LabelEntry("0x4fdd5eb2fb260149a3903859043e962ab89d8ed4", LabelCategory.CEX, "Bitfinex 19"),

    # ─── DEX routers ─────────────────────────────────────────────────────
    LabelEntry("0x7a250d5630b4cf539739df2c5dacb4c659f2488d", LabelCategory.DEX_ROUTER, "Uniswap V2 Router"),
    LabelEntry("0xe592427a0aece92de3edee1f18e0157c05861564", LabelCategory.DEX_ROUTER, "Uniswap V3 Router"),
    LabelEntry("0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45", LabelCategory.DEX_ROUTER, "Uniswap V3 Router 2"),
    LabelEntry("0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b", LabelCategory.DEX_ROUTER, "Uniswap Universal Router"),
    LabelEntry("0x000000000004444c5dc75cb358380d2e3de08a90", LabelCategory.DEX_ROUTER, "Uniswap V4 PoolManager"),
    LabelEntry("0x1111111254eeb25477b68fb85ed929f73a960582", LabelCategory.DEX_ROUTER, "1inch V5 Router"),
    LabelEntry("0x111111125421ca6dc452d289314280a0f8842a65", LabelCategory.DEX_ROUTER, "1inch V6 Router"),
    LabelEntry("0xdef1c0ded9bec7f1a1670819833240f027b25eff", LabelCategory.DEX_ROUTER, "0x Exchange Proxy"),
    LabelEntry("0xdef171fe48cf0115b1d80b88dc8eab59176fee57", LabelCategory.DEX_ROUTER, "Paraswap V5"),
    LabelEntry("0x0000000022d53366457f9d5e68ec105046fc4383", LabelCategory.DEX_ROUTER, "Curve Registry"),

    # ─── Major DEX pools (top-volume WETH pairs) ─────────────────────────
    LabelEntry("0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc", LabelCategory.DEX_POOL, "Uniswap V2: USDC/WETH"),
    LabelEntry("0x0d4a11d5eeaac28ec3f61d100daf4d40471f1852", LabelCategory.DEX_POOL, "Uniswap V2: USDT/WETH"),
    LabelEntry("0xa478c2975ab1ea89e8196811f51a7b7ade33eb11", LabelCategory.DEX_POOL, "Uniswap V2: DAI/WETH"),
    LabelEntry("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", LabelCategory.DEX_POOL, "Uniswap V3: USDC/WETH 0.05%"),
    LabelEntry("0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8", LabelCategory.DEX_POOL, "Uniswap V3: USDC/WETH 0.30%"),
    LabelEntry("0x4e68ccd3e89f51c3074ca5072bbac773960dfa36", LabelCategory.DEX_POOL, "Uniswap V3: USDT/WETH 0.30%"),
    LabelEntry("0x60594a405d53811d3bc4766596efd80fd545a270", LabelCategory.DEX_POOL, "Uniswap V3: DAI/WETH 0.05%"),
    LabelEntry("0xcbcdf9626bc03e24f779434178a73a0b4bad62ed", LabelCategory.DEX_POOL, "Uniswap V3: WBTC/WETH 0.30%"),
    LabelEntry("0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7", LabelCategory.DEX_POOL, "Curve: 3pool"),
    LabelEntry("0xdc24316b9ae028f1497c275eb9192a3ea0f67022", LabelCategory.DEX_POOL, "Curve: stETH/ETH"),
    LabelEntry("0xba12222222228d8ba445958a75a0704d566bf2c8", LabelCategory.DEX_POOL, "Balancer V2 Vault"),

    # ─── Lending protocol pools ──────────────────────────────────────────
    LabelEntry("0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2", LabelCategory.LENDING, "Aave V3 Pool"),
    LabelEntry("0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9", LabelCategory.LENDING, "Aave V2 Pool"),
    LabelEntry("0xc3d688b66703497daa19211eedff47f25384cdc3", LabelCategory.LENDING, "Compound V3: cUSDCv3"),
    LabelEntry("0xa17581a9e3356d9a858b789d68b4d866e593ae94", LabelCategory.LENDING, "Compound V3: cWETHv3"),
    LabelEntry("0x3d9819210a31b4961b30ef54be2aed79b9c9cd3b", LabelCategory.LENDING, "Compound V2 Comptroller"),
    LabelEntry("0x9759a6ac90977b93b58547b4a71c78317f391a28", LabelCategory.LENDING, "Maker DAI Join"),
    LabelEntry("0xc13e21b648a5ee794902342038ff3adab66be987", LabelCategory.LENDING, "Spark Pool"),
    LabelEntry("0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb", LabelCategory.LENDING, "Morpho Blue"),

    # ─── ETH staking / restaking core ────────────────────────────────────
    LabelEntry("0x00000000219ab540356cbb839cbe05303d7705fa", LabelCategory.STAKING, "Beacon Deposit Contract"),
    LabelEntry("0xae7ab96520de3a18e5e111b5eaab095312d7fe84", LabelCategory.STAKING, "Lido stETH"),
    LabelEntry("0x889edc2edab5f40e902b864ad4d7ade8e412f9b1", LabelCategory.STAKING, "Lido withdrawal queue"),
    LabelEntry("0xdd3f50f8a6cafbe9b31a427582963f465e745af8", LabelCategory.STAKING, "Rocket Pool Deposit Pool"),
    LabelEntry("0x1d8f8f00cfa6758d7be78336684788fb0ee0fa46", LabelCategory.STAKING, "Rocket Pool Storage"),
    LabelEntry("0xae78736cd615f374d3085123a210448e74fc6393", LabelCategory.STAKING, "Rocket Pool: rETH"),
    LabelEntry("0xbe9895146f7af43049ca1c1ae358b0541ea49704", LabelCategory.STAKING, "Coinbase: cbETH"),
    LabelEntry("0xac3e018457b222d93114458476f3e3416abbe38f", LabelCategory.STAKING, "Frax: sfrxETH vault"),
    LabelEntry("0xd5f7838f5c461feff7fe49ea5ebaf7728bb0adfa", LabelCategory.STAKING, "Mantle: mETH"),
    LabelEntry("0xf951e335afb289353dc249e82926178eac7ded78", LabelCategory.STAKING, "Swell: swETH"),
    LabelEntry("0xa35b1b31ce002fbf2058d22f30f95d405200a15b", LabelCategory.STAKING, "Stader: ETHx"),
    LabelEntry("0x858646372cc42e1a627fce94aa7a7033e7cf075a", LabelCategory.STAKING, "EigenLayer StrategyManager"),
    LabelEntry("0x91e677b07f7af907ec9a428aafa9fc14a0d3a338", LabelCategory.STAKING, "EigenLayer EigenPodManager"),

    # ─── LRTs (issuer mints / vaults) ────────────────────────────────────
    LabelEntry("0x308861a430be4cce5502d0a12724771fc6daf216", LabelCategory.LRT, "ether.fi Liquidity Pool"),
    LabelEntry("0xcd5fe23c85820f7b72d0926fc9b05b43e359b7ee", LabelCategory.LRT, "ether.fi: weETH"),
    LabelEntry("0x35fa164735182de50811e8e2e824cfb9b6118ac2", LabelCategory.LRT, "ether.fi: eETH"),
    LabelEntry("0x74a09653a083691711cf8215a6ab074bb4e99ef5", LabelCategory.LRT, "Renzo: ezETH deposit"),
    LabelEntry("0xbf5495efe5db9ce00f80364c8b423567e58d2110", LabelCategory.LRT, "Renzo: ezETH"),
    LabelEntry("0x036676389e48133b63a802f8635ad39e752d375d", LabelCategory.LRT, "Kelp DAO: rsETH"),
    LabelEntry("0xd9a442856c234a39a81a089c06451ebaa4306a72", LabelCategory.LRT, "Puffer: pufETH vault"),
    LabelEntry("0xfae103dc9cf190ed75350761e95403b7b8afa6c0", LabelCategory.LRT, "Swell: rswETH"),

    # ─── L1 bridge inboxes for major L2s ─────────────────────────────────
    LabelEntry("0x4dbd4fc535ac27206064b68ffcf827b0a60bab3f", LabelCategory.BRIDGE_L1, "Arbitrum Inbox"),
    LabelEntry("0x8315177ab297ba92a06054ce80a67ed4dbd7ed3a", LabelCategory.BRIDGE_L1, "Arbitrum Bridge"),
    LabelEntry("0xa3a7b6f88361f48403514059f1f16c8e78d60eec", LabelCategory.BRIDGE_L2_GATEWAY, "Arbitrum L1 ERC20 Gateway"),
    LabelEntry("0xbeb5fc579115071764c7423a4f12edde41f106ed", LabelCategory.BRIDGE_L1, "Optimism Portal"),
    LabelEntry("0x99c9fc46f92e8a1c0dec1b1747d010903e884be1", LabelCategory.BRIDGE_L2_GATEWAY, "Optimism L1StandardBridge"),
    LabelEntry("0x49048044d57e1c92a77f79988d21fa8faf74e97e", LabelCategory.BRIDGE_L1, "Base Portal"),
    LabelEntry("0x3154cf16ccdb4c6d922629664174b904d80f2c35", LabelCategory.BRIDGE_L2_GATEWAY, "Base L1StandardBridge"),
    LabelEntry("0x32400084c286cf3e17e7b677ea9583e60a000324", LabelCategory.BRIDGE_L1, "zkSync Era Bridge"),
    LabelEntry("0xd19d4b5d358258f05d7b411e21a1460d11b0876f", LabelCategory.BRIDGE_L1, "Linea Bridge"),
    LabelEntry("0xf8b1378579659d8f7ee5f3c929c2f3e332e41fd6", LabelCategory.BRIDGE_L2_GATEWAY, "Scroll L1 Gateway Router"),

    # ─── Hyperliquid ─────────────────────────────────────────────────────
    # Note: HL's primary bridge is on Arbitrum, not mainnet. The mainnet
    # entry below is the Arbitrum-bridge inbox path users transit through
    # on their way to HL — proxy signal only. See spec for detail.
    LabelEntry("0x2df1c51e09aecf9cacb7bc98cb1742757f163df7", LabelCategory.HYPERLIQUID, "Hyperliquid Bridge2 (Arb)"),

    # ─── Oracles (rare in flow but worth tagging) ────────────────────────
    LabelEntry("0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419", LabelCategory.ORACLE, "Chainlink ETH/USD"),
    LabelEntry("0xf4030086522a5beea4988f8ca5b36dbc97bee88c", LabelCategory.ORACLE, "Chainlink BTC/USD"),
    LabelEntry("0x4305fb66699c3b2702d4d05cf36551390a4c69c6", LabelCategory.ORACLE, "Pyth Receiver"),
)


def get_seed_revision() -> int:
    """Used by the seeder to detect whether the curated set has changed
    since the last upsert. Bump _SEED_REVISION above any time you edit
    CURATED_LABELS — the next worker startup will re-upsert."""
    return _SEED_REVISION
