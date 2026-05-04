"""address label registry (v4 foundation)

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-04

Foundation for the v4 'replace 8 of 9 Dune panels with live on-chain
classification' migration. Single labeled-address registry that the
realtime listener consults to tag every persisted transfer with its
flow_kind (CEX deposit, DEX swap, lending, staking, bridge, etc.).
See docs/superpowers/specs/2026-05-03-v4-flow-classification-vision.md.
"""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "address_label",
        sa.Column("address", sa.String(42), primary_key=True),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("confidence", sa.SmallInteger, nullable=False, server_default="100"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_address_label_category", "address_label", ["category"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_address_label_category", table_name="address_label")
    op.drop_table("address_label")
