"""pending mempool transfers

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_transfers",
        sa.Column("tx_hash", sa.String(66), primary_key=True),
        sa.Column("from_addr", sa.String(42), nullable=False),
        sa.Column("to_addr", sa.String(42), nullable=False),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("usd_value", sa.Numeric(32, 2), nullable=True),
        sa.Column(
            "seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("nonce", sa.BigInteger, nullable=True),
        sa.Column("gas_price_gwei", sa.Numeric(20, 9), nullable=True),
    )
    op.create_index("ix_pending_seen_at_desc", "pending_transfers", [sa.text("seen_at DESC")])
    op.create_index("ix_pending_sender_nonce", "pending_transfers", ["from_addr", "nonce"])


def downgrade() -> None:
    op.drop_index("ix_pending_sender_nonce", table_name="pending_transfers")
    op.drop_index("ix_pending_seen_at_desc", table_name="pending_transfers")
    op.drop_table("pending_transfers")
