"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-23

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_candles",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("timeframe", sa.String(8), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("open", sa.Numeric(24, 8), nullable=False),
        sa.Column("high", sa.Numeric(24, 8), nullable=False),
        sa.Column("low", sa.Numeric(24, 8), nullable=False),
        sa.Column("close", sa.Numeric(24, 8), nullable=False),
        sa.Column("volume", sa.Numeric(32, 8), nullable=False),
    )
    op.create_table(
        "onchain_volume",
        sa.Column("asset", sa.String(16), primary_key=True),
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("tx_count", sa.BigInteger, nullable=False),
        sa.Column("usd_value", sa.Numeric(32, 2), nullable=False),
    )
    op.create_table(
        "exchange_flows",
        sa.Column("exchange", sa.String(32), primary_key=True),
        sa.Column("direction", sa.String(8), primary_key=True),
        sa.Column("asset", sa.String(16), primary_key=True),
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("usd_value", sa.Numeric(32, 2), nullable=False),
    )
    op.create_table(
        "stablecoin_flows",
        sa.Column("asset", sa.String(16), primary_key=True),
        sa.Column("direction", sa.String(8), primary_key=True),
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("usd_value", sa.Numeric(32, 2), nullable=False),
    )
    op.create_table(
        "network_activity",
        sa.Column("ts", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("tx_count", sa.BigInteger, nullable=False),
        sa.Column("gas_price_gwei", sa.Numeric(18, 4), nullable=False),
        sa.Column("base_fee", sa.Numeric(18, 4), nullable=False),
    )
    op.create_table(
        "watched_wallets",
        sa.Column("address", sa.String(42), primary_key=True),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(512), nullable=True),
    )
    op.create_table(
        "transfers",
        sa.Column("tx_hash", sa.String(66), primary_key=True),
        sa.Column("log_index", sa.Integer, primary_key=True),
        sa.Column("block_number", sa.BigInteger, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("from_addr", sa.String(42), nullable=False),
        sa.Column("to_addr", sa.String(42), nullable=False),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("usd_value", sa.Numeric(32, 2), nullable=True),
    )
    op.create_index("ix_transfers_block_number", "transfers", ["block_number"])
    op.create_index("ix_transfers_ts", "transfers", ["ts"])
    op.create_index("ix_transfers_from_addr", "transfers", ["from_addr"])
    op.create_index("ix_transfers_to_addr", "transfers", ["to_addr"])
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("rule_type", sa.String(64), nullable=False),
        sa.Column("params", JSONB, nullable=False),
        sa.Column("channels", JSONB, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("name", name="uq_alert_rules_name"),
    )
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("rule_id", sa.Integer, sa.ForeignKey("alert_rules.id"), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("delivered", JSONB, nullable=False),
    )
    op.create_index("ix_alert_events_rule_id", "alert_events", ["rule_id"])
    op.create_index("ix_alert_events_fired_at", "alert_events", ["fired_at"])


def downgrade() -> None:
    for t in [
        "alert_events",
        "alert_rules",
        "transfers",
        "watched_wallets",
        "network_activity",
        "stablecoin_flows",
        "exchange_flows",
        "onchain_volume",
        "price_candles",
    ]:
        op.drop_table(t)
