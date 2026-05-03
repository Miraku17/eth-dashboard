"""order flow per-dex breakdown

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-03

Adds a `dex` column to order_flow so each (ts_bucket, side) row can split
into per-DEX contributions (uniswap_v2 / uniswap_v3 / curve / balancer /
other). Existing rows get tagged 'aggregate' to preserve continuity
until the next Dune cron tick repopulates the table with per-DEX rows.
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the new column with a default so existing rows are valid.
    op.add_column(
        "order_flow",
        sa.Column("dex", sa.String(16), nullable=False, server_default="aggregate"),
    )

    # Drop and recreate the primary key to include `dex`.
    op.execute("ALTER TABLE order_flow DROP CONSTRAINT order_flow_pkey")
    op.create_primary_key("order_flow_pkey", "order_flow", ["ts_bucket", "dex", "side"])

    # Drop the server_default — going forward, every insert must specify
    # the dex explicitly. Existing 'aggregate' rows keep their value.
    op.alter_column("order_flow", "dex", server_default=None)


def downgrade() -> None:
    op.execute("ALTER TABLE order_flow DROP CONSTRAINT order_flow_pkey")
    op.create_primary_key("order_flow_pkey", "order_flow", ["ts_bucket", "side"])
    op.drop_column("order_flow", "dex")
