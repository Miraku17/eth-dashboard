from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import PendingTransfer, Transfer
from app.workers.pending_cleanup import _cleanup_pending


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(PendingTransfer).delete()
        s.query(Transfer).delete()
        s.commit()
        yield s


def _make_pending(session, tx_hash: str, age_minutes: int) -> PendingTransfer:
    row = PendingTransfer(
        tx_hash=tx_hash,
        from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        to_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        asset="ETH",
        amount=Decimal("100"),
        usd_value=Decimal("300000"),
        seen_at=datetime.now(UTC) - timedelta(minutes=age_minutes),
        nonce=1,
        gas_price_gwei=Decimal("20"),
    )
    session.add(row)
    session.commit()
    return row


def test_cleanup_removes_stale_pending(session):
    _make_pending(session, "0xstale", age_minutes=31)
    _cleanup_pending(session)
    assert session.query(PendingTransfer).count() == 0


def test_cleanup_keeps_recent_pending(session):
    _make_pending(session, "0xfresh", age_minutes=5)
    _cleanup_pending(session)
    assert session.query(PendingTransfer).count() == 1


def test_cleanup_removes_now_confirmed_pending(session):
    _make_pending(session, "0xconfirmed", age_minutes=2)
    confirmed = Transfer(
        tx_hash="0xconfirmed",
        log_index=0,
        block_number=24_000_000,
        ts=datetime.now(UTC),
        from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        to_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        asset="ETH",
        amount=Decimal("100"),
        usd_value=Decimal("300000"),
    )
    session.add(confirmed)
    session.commit()
    _cleanup_pending(session)
    assert session.query(PendingTransfer).count() == 0


def test_cleanup_keeps_distinct_pending_when_others_confirmed(session):
    _make_pending(session, "0xstillpending", age_minutes=5)
    _make_pending(session, "0xconfirmed", age_minutes=5)
    confirmed = Transfer(
        tx_hash="0xconfirmed",
        log_index=0,
        block_number=24_000_000,
        ts=datetime.now(UTC),
        from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        to_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        asset="ETH",
        amount=Decimal("100"),
        usd_value=Decimal("300000"),
    )
    session.add(confirmed)
    session.commit()
    _cleanup_pending(session)
    remaining = [r.tx_hash for r in session.query(PendingTransfer).all()]
    assert remaining == ["0xstillpending"]
