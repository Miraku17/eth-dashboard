"""bridge flows

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-03

"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bridge_flows",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("bridge", sa.String(16), primary_key=True),
        sa.Column("direction", sa.String(8), primary_key=True),
        sa.Column("asset", sa.String(16), primary_key=True),
        sa.Column("usd_value", sa.Numeric(38, 6), nullable=False),
        sa.CheckConstraint(
            "direction IN ('in','out')",
            name="bridge_flows_direction_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("bridge_flows")
