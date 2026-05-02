"""lst supply

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-02

"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lst_supply",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("token", sa.String(10), primary_key=True),
        sa.Column("supply", sa.Numeric(38, 18), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("lst_supply")
