"""perp copy-trading: perp_wallet_score + perp_watchlist

Adds two tables for the v5-perp-copy-trading subsystem:

- perp_wallet_score: daily 90d snapshot per wallet of GMX V2 perp trading
  performance (trades, win rate, long/short split, realized PnL, avg hold,
  avg position, avg leverage). Latest-only — each daily cron run rewrites
  the wallet's row. Backs the /copy-trading leaderboard.
- perp_watchlist: operator-curated set of wallets to alert on, with a
  per-watch min_notional_usd floor (default $25,000) to suppress
  scale-in noise.

The leaderboard partial index covers the default filter predicate
(>=30 trades, >=60% win rate, >=$10k realized PnL) so leaderboard
queries are single index scans rather than full-table filters.

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-17
"""
import sqlalchemy as sa
from alembic import op

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
    op.create_index(
        "perp_wallet_score_leaderboard_idx",
        "perp_wallet_score",
        [sa.text("realized_pnl_90d DESC")],
        postgresql_where=sa.text(
            "trades_90d >= 30 AND win_rate_90d >= 0.6 AND realized_pnl_90d >= 10000"
        ),
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
    op.drop_index("perp_wallet_score_leaderboard_idx", table_name="perp_wallet_score")
    op.drop_table("perp_wallet_score")
