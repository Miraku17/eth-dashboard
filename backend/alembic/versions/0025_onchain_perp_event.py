"""onchain perp events (GMX V2 — Arbitrum)

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-06

Foundation table for the post-v4 on-chain-perps track. One row per
PositionIncrease / PositionDecrease (incl. Liquidation orderType) event
emitted by the GMX V2 EventEmitter. Kept event-sourced so open positions,
liquidations feed, and history all derive from a single source of truth.
"""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onchain_perp_event",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("venue", sa.String(16), nullable=False),
        sa.Column("account", sa.String(42), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("event_kind", sa.String(16), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("size_usd", sa.Numeric(38, 6), nullable=False),
        sa.Column("size_after_usd", sa.Numeric(38, 6), nullable=False),
        sa.Column("collateral_usd", sa.Numeric(38, 6), nullable=False),
        sa.Column("leverage", sa.Numeric(12, 4), nullable=False),
        sa.Column("price_usd", sa.Numeric(38, 6), nullable=False),
        sa.Column("pnl_usd", sa.Numeric(38, 6), nullable=True),
        sa.Column("tx_hash", sa.String(66), nullable=False),
        sa.Column("log_index", sa.Integer, nullable=False),
        sa.UniqueConstraint("tx_hash", "log_index", name="uq_onchain_perp_event_tx_log"),
    )
    op.create_index("ix_onchain_perp_event_ts", "onchain_perp_event", ["ts"], unique=False)
    op.create_index(
        "ix_onchain_perp_event_account_ts",
        "onchain_perp_event",
        ["account", "ts"],
        unique=False,
    )
    op.create_index(
        "ix_onchain_perp_event_kind_ts",
        "onchain_perp_event",
        ["event_kind", "ts"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_onchain_perp_event_kind_ts", table_name="onchain_perp_event")
    op.drop_index("ix_onchain_perp_event_account_ts", table_name="onchain_perp_event")
    op.drop_index("ix_onchain_perp_event_ts", table_name="onchain_perp_event")
    op.drop_table("onchain_perp_event")
