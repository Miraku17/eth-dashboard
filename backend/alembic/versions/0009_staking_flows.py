"""staking flows

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-02

"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staking_flows",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("kind", sa.String(20), primary_key=True),
        sa.Column("amount_eth", sa.Numeric(38, 18), nullable=False),
        sa.Column("amount_usd", sa.Numeric(38, 6), nullable=True),
        sa.CheckConstraint(
            "kind IN ('deposit','withdrawal_partial','withdrawal_full')",
            name="staking_flows_kind_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("staking_flows")
