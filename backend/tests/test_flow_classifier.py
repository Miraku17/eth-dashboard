"""Tests for the live flow classifier (v4)."""
from app.realtime.flow_classifier import FlowKind, classify
from app.services.address_labels import LabelCategory


def test_unlabeled_both_sides() -> None:
    assert classify(None, None) == FlowKind.WALLET_TO_WALLET


def test_wallet_to_cex_deposit() -> None:
    # User wallet -> Binance hot. Bearish, deposit direction.
    assert classify(None, LabelCategory.CEX) == FlowKind.WALLET_TO_CEX


def test_cex_to_wallet_withdrawal() -> None:
    # Binance hot -> user wallet. Bullish, withdrawal direction.
    assert classify(LabelCategory.CEX, None) == FlowKind.CEX_TO_WALLET


def test_wallet_to_dex_swap() -> None:
    # Wallet -> Uniswap router. Selling into the DEX.
    assert classify(None, LabelCategory.DEX_ROUTER) == FlowKind.WALLET_TO_DEX
    assert classify(None, LabelCategory.DEX_POOL) == FlowKind.WALLET_TO_DEX


def test_dex_to_wallet_buy() -> None:
    assert classify(LabelCategory.DEX_POOL, None) == FlowKind.DEX_TO_WALLET


def test_lending_directions() -> None:
    assert classify(None, LabelCategory.LENDING) == FlowKind.LENDING_DEPOSIT
    assert classify(LabelCategory.LENDING, None) == FlowKind.LENDING_WITHDRAW


def test_staking_and_lrt_directions() -> None:
    assert classify(None, LabelCategory.STAKING) == FlowKind.STAKING_DEPOSIT
    assert classify(LabelCategory.STAKING, None) == FlowKind.STAKING_UNSTAKE
    assert classify(None, LabelCategory.LRT) == FlowKind.STAKING_DEPOSIT
    assert classify(LabelCategory.LRT, None) == FlowKind.STAKING_UNSTAKE


def test_bridge_directions() -> None:
    assert classify(None, LabelCategory.BRIDGE_L1) == FlowKind.BRIDGE_L2_DEPOSIT
    assert classify(LabelCategory.BRIDGE_L1, None) == FlowKind.BRIDGE_L2_WITHDRAW


def test_hyperliquid_directions() -> None:
    assert classify(None, LabelCategory.HYPERLIQUID) == FlowKind.HYPERLIQUID_IN
    assert classify(LabelCategory.HYPERLIQUID, None) == FlowKind.HYPERLIQUID_OUT


def test_cex_wins_tie_when_both_labeled() -> None:
    # DEX pool sends to a CEX hot wallet (e.g. routed swap path).
    # CEX is the more impactful signal — should resolve to a CEX flow.
    # Direction follows the CEX side: CEX is the `to` end → wallet_to_cex.
    result = classify(LabelCategory.DEX_POOL, LabelCategory.CEX)
    assert result == FlowKind.WALLET_TO_CEX


def test_cex_wins_tie_other_direction() -> None:
    # CEX hot wallet sends to a DEX pool (rare; CEX-side liquidity tx).
    # Direction follows the CEX side: CEX is the `from` end → cex_to_wallet.
    result = classify(LabelCategory.CEX, LabelCategory.DEX_POOL)
    assert result == FlowKind.CEX_TO_WALLET


def test_unknown_category_falls_back() -> None:
    # Unrecognized category string defaults to wallet_to_wallet.
    assert classify(None, "unknown_made_up_category") == FlowKind.WALLET_TO_WALLET
