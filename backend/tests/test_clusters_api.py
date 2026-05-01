"""End-to-end clusters API: cache hit, cache miss, refresh, stale-fallback."""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.api.schemas import ClusterResult, ClusterStats
from app.core.models import WalletCluster


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(WalletCluster).delete()
        s.commit()
        yield s


def _store_cache_row(session, address: str, payload: dict, ttl_expires_at: datetime):
    row = WalletCluster(
        address=address,
        computed_at=ttl_expires_at - timedelta(days=7),
        ttl_expires_at=ttl_expires_at,
        payload=payload,
    )
    session.add(row)
    session.commit()


def _fresh_payload(address: str) -> dict:
    return ClusterResult(
        address=address,
        computed_at=datetime.now(UTC),
        labels=["Some Label"],
        linked_wallets=[],
        stats=ClusterStats(),
    ).model_dump(mode="json")


def test_get_cluster_returns_cached_result(auth_client, session):
    addr = "0x" + "1" * 40
    _store_cache_row(session, addr, _fresh_payload(addr),
                     datetime.now(UTC) + timedelta(days=3))
    r = auth_client.get(f"/api/clusters/{addr}")
    assert r.status_code == 200, r.text
    assert r.json()["address"] == addr
    assert r.json()["stale"] is False


def test_get_cluster_computes_when_no_cache(auth_client, session):
    addr = "0x" + "2" * 40

    fake = ClusterResult(address=addr, computed_at=datetime.now(UTC))
    with patch("app.api.clusters._compute_for_address", AsyncMock(return_value=fake)):
        r = auth_client.get(f"/api/clusters/{addr}")
    assert r.status_code == 200, r.text
    assert r.json()["address"] == addr

    # And it was upserted into the cache.
    row = session.get(WalletCluster, addr)
    assert row is not None


def test_post_refresh_busts_cache_and_recomputes(auth_client, session):
    addr = "0x" + "3" * 40
    _store_cache_row(session, addr, _fresh_payload(addr),
                     datetime.now(UTC) + timedelta(days=3))

    new = ClusterResult(address=addr, computed_at=datetime.now(UTC),
                        labels=["After Refresh"])
    with patch("app.api.clusters._compute_for_address", AsyncMock(return_value=new)):
        r = auth_client.post(f"/api/clusters/{addr}/refresh")
    assert r.status_code == 200, r.text
    assert r.json()["labels"] == ["After Refresh"]


def test_get_cluster_serves_stale_during_etherscan_outage(auth_client, session):
    """Expired row + Etherscan unavailable → return stale row with stale=true."""
    from app.clients.etherscan import EtherscanUnavailable
    addr = "0x" + "4" * 40
    _store_cache_row(session, addr, _fresh_payload(addr),
                     datetime.now(UTC) - timedelta(days=1))  # expired

    with patch("app.api.clusters._compute_for_address",
               AsyncMock(side_effect=EtherscanUnavailable("down"))):
        r = auth_client.get(f"/api/clusters/{addr}")
    assert r.status_code == 200, r.text
    assert r.json()["stale"] is True


def test_get_cluster_503_when_no_cache_and_etherscan_down(auth_client):
    from app.clients.etherscan import EtherscanUnavailable
    addr = "0x" + "5" * 40
    with patch("app.api.clusters._compute_for_address",
               AsyncMock(side_effect=EtherscanUnavailable("down"))):
        r = auth_client.get(f"/api/clusters/{addr}")
    assert r.status_code == 503


def test_malformed_address_returns_400(auth_client):
    r = auth_client.get("/api/clusters/not-an-address")
    assert r.status_code == 400
