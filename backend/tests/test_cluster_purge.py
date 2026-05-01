from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import WalletCluster
from app.workers.cluster_jobs import purge_expired_clusters


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(WalletCluster).delete()
        s.commit()
        yield s


async def test_purge_deletes_rows_older_than_grace_period(session):
    now = datetime.now(UTC)
    session.add_all([
        # fresh — keep
        WalletCluster(
            address="0x" + "a" * 40,
            computed_at=now,
            ttl_expires_at=now + timedelta(days=3),
            payload={},
        ),
        # expired but within grace — keep
        WalletCluster(
            address="0x" + "b" * 40,
            computed_at=now - timedelta(days=8),
            ttl_expires_at=now - timedelta(days=1),
            payload={},
        ),
        # expired beyond grace — delete
        WalletCluster(
            address="0x" + "c" * 40,
            computed_at=now - timedelta(days=20),
            ttl_expires_at=now - timedelta(days=8),
            payload={},
        ),
    ])
    session.commit()

    deleted = await purge_expired_clusters({"_db_session_for_test": session})

    assert deleted == 1
    session.expire_all()
    surviving = {row.address for row in session.query(WalletCluster).all()}
    assert "0x" + "c" * 40 not in surviving
    assert "0x" + "a" * 40 in surviving
    assert "0x" + "b" * 40 in surviving
