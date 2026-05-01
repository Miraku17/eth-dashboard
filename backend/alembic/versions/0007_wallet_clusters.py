"""wallet clusters

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallet_clusters",
        sa.Column("address", sa.String(42), primary_key=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
    )
    op.create_index(
        "ix_wallet_clusters_ttl_expires_at",
        "wallet_clusters",
        ["ttl_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_wallet_clusters_ttl_expires_at", table_name="wallet_clusters")
    op.drop_table("wallet_clusters")
