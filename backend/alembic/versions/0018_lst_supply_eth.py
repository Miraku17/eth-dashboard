"""lst supply eth_supply column

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-03

"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lst_supply",
        sa.Column("eth_supply", sa.Numeric(38, 18), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lst_supply", "eth_supply")
