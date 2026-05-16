"""perp copy-trading: perp_wallet_score + perp_watchlist

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "perp_wallet_score",
        sa.Column("wallet", sa.String(42), primary_key=True),
        sa.Column("trades_90d", sa.Integer, nullable=False),
        sa.Column("win_rate_90d", sa.Numeric(5, 4), nullable=False),
        sa.Column("win_rate_long_90d", sa.Numeric(5, 4), nullable=True),
        sa.Column("win_rate_short_90d", sa.Numeric(5, 4), nullable=True),
        sa.Column("realized_pnl_90d", sa.Numeric(20, 2), nullable=False),
        sa.Column("avg_hold_secs", sa.Integer, nullable=False),
        sa.Column("avg_position_usd", sa.Numeric(20, 2), nullable=False),
        sa.Column("avg_leverage", sa.Numeric(6, 2), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.execute(
        """
        CREATE INDEX perp_wallet_score_leaderboard_idx
          ON perp_wallet_score (realized_pnl_90d DESC)
          WHERE trades_90d >= 30
            AND win_rate_90d >= 0.6
            AND realized_pnl_90d >= 10000
        """
    )
    op.create_table(
        "perp_watchlist",
        sa.Column("wallet", sa.String(42), primary_key=True),
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column(
            "min_notional_usd",
            sa.Numeric(20, 2),
            server_default="25000",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("perp_watchlist")
    op.execute("DROP INDEX IF EXISTS perp_wallet_score_leaderboard_idx")
    op.drop_table("perp_wallet_score")
