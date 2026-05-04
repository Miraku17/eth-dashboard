"""dex_swap (per-event) + wallet_score (computed snapshot)

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-04

Foundation for the v4 wallet-performance-scoring card. dex_swap captures
each Swap event the realtime listener decodes (V2/V3/Curve/Balancer) along
with the originating EOA so we can compute per-wallet FIFO PnL + win rate.
wallet_score holds the latest computed snapshot, updated by a daily cron.
"""
import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dex_swap",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tx_hash", sa.String(66), nullable=False),
        sa.Column("log_index", sa.Integer, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("wallet", sa.String(42), nullable=False),
        sa.Column("dex", sa.String(16), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("weth_amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("usd_value", sa.Numeric(38, 6), nullable=False),
        sa.UniqueConstraint("tx_hash", "log_index", name="uq_dex_swap_tx_log"),
    )
    op.create_index("ix_dex_swap_wallet_ts", "dex_swap", ["wallet", "ts"], unique=False)
    op.create_index("ix_dex_swap_ts", "dex_swap", ["ts"], unique=False)

    op.create_table(
        "wallet_score",
        sa.Column("wallet", sa.String(42), primary_key=True),
        # 30-day window — kept simple in v1. 90/365d windows can be added
        # later as separate columns; the cron just needs more SELECTs.
        sa.Column("trades_30d", sa.Integer, nullable=False, server_default="0"),
        sa.Column("volume_usd_30d", sa.Numeric(38, 2), nullable=False, server_default="0"),
        sa.Column("realized_pnl_30d", sa.Numeric(38, 2), nullable=False, server_default="0"),
        # win_rate is nullable — wallets with <N round-trips can't be scored.
        sa.Column("win_rate_30d", sa.Float, nullable=True),
        # Composite score the panel will sort by. Larger = "smarter".
        sa.Column("score", sa.Float, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_wallet_score_score", "wallet_score", ["score"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_wallet_score_score", table_name="wallet_score")
    op.drop_table("wallet_score")
    op.drop_index("ix_dex_swap_ts", table_name="dex_swap")
    op.drop_index("ix_dex_swap_wallet_ts", table_name="dex_swap")
    op.drop_table("dex_swap")
