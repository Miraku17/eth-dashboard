"""mantle order flow (Agni V3 — Mantle Network)

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-10

Hourly buy/sell pressure for MNT on Mantle DEXes. v1 only writes
dex='agni' but the column is sized for more. Storing raw MNT volume
keeps the writer price-independent — the API multiplies by a Redis-
cached CoinGecko MNT/USD snapshot at read time.
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mantle_order_flow",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dex", sa.String(16), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("count", sa.BigInteger, nullable=False),
        sa.Column("mnt_amount", sa.Numeric(38, 18), nullable=False),
        sa.PrimaryKeyConstraint("ts_bucket", "dex", "side"),
    )
    op.create_index(
        "ix_mantle_order_flow_ts",
        "mantle_order_flow",
        ["ts_bucket"],
        unique=False,
        postgresql_using="btree",
        postgresql_ops={"ts_bucket": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_mantle_order_flow_ts", table_name="mantle_order_flow")
    op.drop_table("mantle_order_flow")
