import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.models import AlertEvent, AlertRule
from app.main import app


@pytest.fixture
def clean(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(AlertEvent).delete()
        s.query(AlertRule).delete()
        s.commit()
        yield s


def test_create_list_patch_delete_rule(clean):
    client = TestClient(app)
    r = client.post(
        "/api/alerts/rules",
        json={
            "name": "ETH>4000",
            "params": {"rule_type": "price_above", "threshold": 4000},
            "channels": [{"type": "telegram"}],
            "cooldown_min": 30,
        },
    )
    assert r.status_code == 200, r.text
    rule_id = r.json()["id"]
    assert r.json()["rule_type"] == "price_above"
    assert r.json()["cooldown_min"] == 30
    assert r.json()["params"]["threshold"] == 4000

    r = client.get("/api/alerts/rules")
    assert r.status_code == 200
    assert len(r.json()["rules"]) == 1

    r = client.patch(f"/api/alerts/rules/{rule_id}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    r = client.delete(f"/api/alerts/rules/{rule_id}")
    assert r.status_code == 204

    r = client.get("/api/alerts/rules")
    assert r.json()["rules"] == []


def test_create_duplicate_name_conflict(clean):
    client = TestClient(app)
    body = {
        "name": "dup",
        "params": {"rule_type": "price_below", "threshold": 1000},
        "channels": [],
    }
    assert client.post("/api/alerts/rules", json=body).status_code == 200
    r2 = client.post("/api/alerts/rules", json=body)
    assert r2.status_code == 409


def test_create_invalid_params_422(clean):
    client = TestClient(app)
    r = client.post(
        "/api/alerts/rules",
        json={
            "name": "bad",
            "params": {"rule_type": "price_above", "threshold": -1},
            "channels": [],
        },
    )
    assert r.status_code == 422


def test_events_endpoint(clean):
    client = TestClient(app)
    client.post(
        "/api/alerts/rules",
        json={
            "name": "x",
            "params": {"rule_type": "price_above", "threshold": 100},
            "channels": [],
        },
    )
    r = client.get("/api/alerts/events?hours=1")
    assert r.status_code == 200
    assert r.json()["events"] == []
