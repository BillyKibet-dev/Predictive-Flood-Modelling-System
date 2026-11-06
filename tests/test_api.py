"""Legacy API regression tests with real JWTs and isolated application records."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.config import settings
from src.api.database import Base, get_db
from src.api.main import app
from src.api.models.db_models import AlertNotification, CitizenReport, FloodPrediction, User, Zone
from src.api.utils.security import hash_password

TEST_PASSWORD = "synthetic-fixture-only-password"


@pytest.fixture(scope="module")
def password_hash():
    return hash_password(TEST_PASSWORD)


@pytest.fixture
def api(password_hash, monkeypatch):
    # Never initialise, seed, query or mutate the configured PostgreSQL database.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    zone = Zone(id="mathare", name="Fixture Mathare", sub_county="fixture", latitude=-1.26, longitude=36.86)
    db.add(zone)
    db.add_all([User(name="Fixture administrator", email="admin@example.test", role="admin", status="Active", password_hash=password_hash),
                User(name="Fixture officer", email="officer@example.test", role="officer", status="Active", password_hash=password_hash)])
    db.flush()
    prediction = FloodPrediction(zone_id=zone.id, timestamp=datetime.now(timezone.utc), risk_level="High", risk_class=2,
                                 confidence_score=.75, model_version="fixture_legacy")
    db.add(prediction)
    db.flush()
    db.add(AlertNotification(id=1, prediction_id=prediction.id, zone_id=zone.id, risk_level="High",
                             timestamp=datetime.now(timezone.utc), acknowledged_status=False))
    db.commit()
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(settings, "AUTO_CREATE_LEGACY_TABLES", False)
    monkeypatch.setattr(settings, "LEGACY_SCHEDULER_ENABLED", False)
    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        db.close()
        engine.dispose()


def login(client, role):
    response = client.post("/auth/login", json={"email": f"{role}@example.test", "password": TEST_PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_health_check(api):
    response = api[0].get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "online"
    assert response.json()["legacy_scheduler_enabled"] is False


def test_login_success(api):
    client, db = api
    response = client.post("/auth/login", json={"email": "admin@example.test", "password": TEST_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["user"]["role"] == "admin"
    assert db.query(User).filter(User.role == "admin").one().last_login is not None
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["role"] == "admin"


def test_login_wrong_password(api):
    response = api[0].post("/auth/login", json={"email": "admin@example.test", "password": "invalid-fixture-input"})
    assert response.status_code == 401


def test_get_predictions_public(api):
    response = api[0].get("/predictions")
    assert response.status_code == 200
    assert response.json()[0]["model_version"] == "fixture_legacy"


def test_get_dashboard_public(api):
    response = api[0].get("/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert len(body["zones"]) == 1 and body["last_updated"]
    assert body["prediction_context"]["spatial_scope"] == "shared_nairobi_weather"


def test_submit_citizen_report(api):
    client, db = api
    response = client.post("/citizen-report", json={"zone_id": "mathare", "observed_condition": "Street flooding", "perceived_severity": "Serious"})
    assert response.status_code == 201
    assert db.query(CitizenReport).count() == 1


def test_get_alerts_requires_auth(api):
    assert api[0].get("/alerts").status_code == 401


def test_get_alerts_with_auth(api):
    client, _ = api
    response = client.get("/alerts", headers={"Authorization": f"Bearer {login(client, 'officer')}"})
    assert response.status_code == 200 and response.json()["total"] == 1


def test_acknowledge_alert(api):
    client, db = api
    headers = {"Authorization": f"Bearer {login(client, 'officer')}"}
    response = client.post("/alerts/1/acknowledge", headers=headers)
    assert response.status_code == 200 and response.json()["acknowledged_status"] is True
    assert db.query(AlertNotification).one().acknowledged_by == db.query(User).filter(User.role == "officer").one().id
    assert client.post("/alerts/1/acknowledge", headers=headers).status_code == 400
    assert client.post("/alerts/999/acknowledge", headers=headers).status_code == 404


def test_admin_get_users_requires_admin(api):
    client, _ = api
    assert client.get("/admin/users", headers={"Authorization": f"Bearer {login(client, 'officer')}"}).status_code == 403


def test_admin_get_users_as_admin(api):
    client, _ = api
    response = client.get("/admin/users", headers={"Authorization": f"Bearer {login(client, 'admin')}"})
    assert response.status_code == 200 and len(response.json()) == 2
    assert all("password_hash" not in user for user in response.json())
