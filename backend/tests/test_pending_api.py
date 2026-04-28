from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.db import get_session
from app.core.models import PendingTransfer
from app.main import app


def test_pending_endpoint_returns_rows_sorted_desc(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)

    def override_get_session():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session

    with Session() as s:
        s.query(PendingTransfer).delete()
        now = datetime.now(UTC)
        s.add_all([
            PendingTransfer(
                tx_hash="0xolder",
                from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                to_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                asset="ETH",
                amount=Decimal("150"),
                usd_value=Decimal("450000"),
                seen_at=now - timedelta(seconds=30),
                nonce=1,
                gas_price_gwei=Decimal("20"),
            ),
            PendingTransfer(
                tx_hash="0xnewer",
                from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                to_addr="0xcccccccccccccccccccccccccccccccccccccccc",
                asset="USDT",
                amount=Decimal("500000"),
                usd_value=Decimal("500000"),
                seen_at=now - timedelta(seconds=5),
                nonce=2,
                gas_price_gwei=Decimal("25"),
            ),
        ])
        s.commit()

    try:
        client = TestClient(app)
        resp = client.get("/api/whales/pending")
        assert resp.status_code == 200
        data = resp.json()
        assert "pending" in data
        hashes = [r["tx_hash"] for r in data["pending"]]
        assert hashes == ["0xnewer", "0xolder"]
        # USD value present and correct
        assert float(data["pending"][0]["usd_value"]) == 500000.0
    finally:
        app.dependency_overrides.clear()


def test_pending_endpoint_empty_returns_empty_list(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)

    def override_get_session():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session

    with Session() as s:
        s.query(PendingTransfer).delete()
        s.commit()

    try:
        client = TestClient(app)
        resp = client.get("/api/whales/pending")
        assert resp.status_code == 200
        assert resp.json() == {"pending": []}
    finally:
        app.dependency_overrides.clear()
