"""Live flow classifier — maps a (from_label, to_label) pair to a
`flow_kind` enum value the panel and tiles can filter on.

Pure function. Called once per persisted whale transfer in the realtime
listener; result lands in the `transfers.flow_kind` column.

Design notes:
* When BOTH sides are labeled, we pick the more impactful side. CEX wins
  every tie (price-impacting), then DEX, then lending/staking/bridge.
  Pure wallet-to-wallet only when neither side has a label.
* Direction matters: a transfer FROM a CEX hot wallet to a wallet is a
  withdrawal (cex_to_wallet); the reverse is a deposit (wallet_to_cex).
  Same for the other categories.
* Unknown label categories (e.g. an `oracle` transfer to a `treasury`)
  fall through to `wallet_to_wallet` rather than inventing new kinds.
"""
from __future__ import annotations

from app.services.address_labels import LabelCategory


class FlowKind:
    """Stable enum-like values written to `transfers.flow_kind`.

    Naming convention: `<src>_to_<dst>` where src/dst describe the
    POSITION's role from the user's perspective. wallet_to_cex = the
    user's wallet sent funds to a CEX hot wallet (deposit, bearish for
    price impact). cex_to_wallet = withdrawal (bullish).
    """
    WALLET_TO_CEX = "wallet_to_cex"           # CEX deposit (bearish)
    CEX_TO_WALLET = "cex_to_wallet"           # CEX withdrawal (bullish)
    WALLET_TO_DEX = "wallet_to_dex"           # selling into a DEX
    DEX_TO_WALLET = "dex_to_wallet"           # buying out of a DEX
    LENDING_DEPOSIT = "lending_deposit"       # supply into Aave/Comp/etc
    LENDING_WITHDRAW = "lending_withdraw"     # redeem from Aave/Comp/etc
    STAKING_DEPOSIT = "staking_deposit"       # ETH → beacon/Lido/RP
    STAKING_UNSTAKE = "staking_unstake"       # withdrawal from staking
    BRIDGE_L2_DEPOSIT = "bridge_l2"           # mainnet → L2
    BRIDGE_L2_WITHDRAW = "bridge_l2_withdraw" # L2 → mainnet
    HYPERLIQUID_IN = "hyperliquid_in"         # toward Hyperliquid bridge
    HYPERLIQUID_OUT = "hyperliquid_out"       # outflow from HL
    WALLET_TO_WALLET = "wallet_to_wallet"     # default — neither side labeled


# Priority order for tie-breaking when BOTH from and to are labeled.
# Lower index = wins. CEX wins over everything because exchange flows
# are the highest-priority signal per the v4 vision (20× weight).
_TIE_BREAK_ORDER = (
    LabelCategory.CEX,
    LabelCategory.HYPERLIQUID,
    LabelCategory.DEX_ROUTER,
    LabelCategory.DEX_POOL,
    LabelCategory.LENDING,
    LabelCategory.STAKING,
    LabelCategory.LRT,
    LabelCategory.BRIDGE_L1,
    LabelCategory.BRIDGE_L2_GATEWAY,
    LabelCategory.ORACLE,
    LabelCategory.MEV,
    LabelCategory.TREASURY,
    LabelCategory.SMART_CONTRACT,
)


def _priority(cat: str | None) -> int:
    if cat is None:
        return 999
    try:
        return _TIE_BREAK_ORDER.index(cat)
    except ValueError:
        return 998


def _kind_for_outbound(cat: str) -> str:
    """from is wallet, to is the labeled side. Wallet sending TO a labeled
    contract → it's a deposit/sell/lock from the user's perspective."""
    if cat == LabelCategory.CEX:
        return FlowKind.WALLET_TO_CEX
    if cat in (LabelCategory.DEX_ROUTER, LabelCategory.DEX_POOL):
        return FlowKind.WALLET_TO_DEX
    if cat == LabelCategory.LENDING:
        return FlowKind.LENDING_DEPOSIT
    if cat in (LabelCategory.STAKING, LabelCategory.LRT):
        return FlowKind.STAKING_DEPOSIT
    if cat in (LabelCategory.BRIDGE_L1, LabelCategory.BRIDGE_L2_GATEWAY):
        return FlowKind.BRIDGE_L2_DEPOSIT
    if cat == LabelCategory.HYPERLIQUID:
        return FlowKind.HYPERLIQUID_IN
    return FlowKind.WALLET_TO_WALLET


def _kind_for_inbound(cat: str) -> str:
    """from is the labeled side, to is wallet. Labeled contract sending
    TO a wallet → user is RECEIVING (withdrawal/buy/unstake)."""
    if cat == LabelCategory.CEX:
        return FlowKind.CEX_TO_WALLET
    if cat in (LabelCategory.DEX_ROUTER, LabelCategory.DEX_POOL):
        return FlowKind.DEX_TO_WALLET
    if cat == LabelCategory.LENDING:
        return FlowKind.LENDING_WITHDRAW
    if cat in (LabelCategory.STAKING, LabelCategory.LRT):
        return FlowKind.STAKING_UNSTAKE
    if cat in (LabelCategory.BRIDGE_L1, LabelCategory.BRIDGE_L2_GATEWAY):
        return FlowKind.BRIDGE_L2_WITHDRAW
    if cat == LabelCategory.HYPERLIQUID:
        return FlowKind.HYPERLIQUID_OUT
    return FlowKind.WALLET_TO_WALLET


def classify(from_category: str | None, to_category: str | None) -> str:
    """Return the flow_kind for a transfer given each side's category.

    Both categories can be None (truly wallet-to-wallet). When both are
    set, the higher-priority side wins per `_TIE_BREAK_ORDER`. The
    direction is then derived from whether that winning side is the
    `from` or `to` end.
    """
    # Fast paths.
    if from_category is None and to_category is None:
        return FlowKind.WALLET_TO_WALLET
    if from_category is None and to_category is not None:
        return _kind_for_outbound(to_category)
    if from_category is not None and to_category is None:
        return _kind_for_inbound(from_category)

    # Both labeled. Pick the more impactful side.
    if _priority(from_category) <= _priority(to_category):
        return _kind_for_inbound(from_category)  # type: ignore[arg-type]
    return _kind_for_outbound(to_category)  # type: ignore[arg-type]
