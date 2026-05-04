"""flow_kind column on transfers + pending_transfers (v4)

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-04

Adds the flow_kind tag the realtime classifier writes on every transfer.
Nullable: existing rows get NULL until a one-shot backfill job scores
them against the address_label registry.
"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transfers",
        sa.Column("flow_kind", sa.String(24), nullable=True),
    )
    op.create_index(
        "ix_transfers_flow_kind", "transfers", ["flow_kind"], unique=False
    )
    op.add_column(
        "pending_transfers",
        sa.Column("flow_kind", sa.String(24), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pending_transfers", "flow_kind")
    op.drop_index("ix_transfers_flow_kind", table_name="transfers")
    op.drop_column("transfers", "flow_kind")
