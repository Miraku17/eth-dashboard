"""widen protocol_tvl.asset to varchar(64)

Some DefiLlama protocols (e.g. Pendle's PT/YT yield tokens) report asset
symbols longer than 20 chars. First sync hit a StringDataRightTruncation
on Pendle rows; bump the column.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-02

"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "protocol_tvl",
        "asset",
        existing_type=sa.String(20),
        type_=sa.String(64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "protocol_tvl",
        "asset",
        existing_type=sa.String(64),
        type_=sa.String(20),
        existing_nullable=False,
    )
