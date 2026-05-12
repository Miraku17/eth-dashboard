"""stable_supply (per-asset circulating supply snapshots)

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-12

Time-series of `totalSupply()` reads for the 16 tracked stables. The
`supply` column stores the raw on-chain integer (post-decimal-scaling
into a float for ease of consumption); `supply_usd` is amount × the
hand-curated `price_usd_approx` per token so the read path doesn't have
to multiply.

Populated by two writers:
  - hourly `sync_stable_supply` cron: live JSON-RPC reads.
  - one-shot `backfill_stable_supply` task: seeds historical daily
    rows from DefiLlama so 1d / 1w / 1M timeframes have history
    before the live cron has run long enough.
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stable_supply",
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("supply", sa.Numeric(38, 6), nullable=False),
        sa.Column("supply_usd", sa.Numeric(38, 2), nullable=False),
        sa.PrimaryKeyConstraint("ts", "asset"),
    )
    op.create_index(
        "ix_stable_supply_ts",
        "stable_supply",
        [sa.text("ts DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_stable_supply_ts", table_name="stable_supply")
    op.drop_table("stable_supply")
