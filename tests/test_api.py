"""Smoke tests for the NairobiFloodWatch API.

Requires a running PostgreSQL database that has been initialised and seeded
via `python -m src.scripts.init_db` before running `pytest tests/ -v`.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def admin_token():
    resp = client.post("/auth/login", json={"email": "admin@flood.ke", "password": "admin123"})
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def officer_token():
    resp = client.post("/auth/login", json={"email": "officer@flood.ke", "password": "officer123"})
    return resp.json()["access_token"]


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "online"


def test_login_success():
    resp = client.post("/auth/login", json={"email": "admin@flood.ke", "password": "admin123"})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_wrong_password():
    resp = client.post("/auth/login", json={"email": "admin@flood.ke", "password": "wrong"})
    assert resp.status_code == 401


def test_get_predictions_public():
    resp = client.get("/predictions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_dashboard_public():
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert "zones" in body
    assert "last_updated" in body


def test_submit_citizen_report():
    resp = client.post(
        "/citizen-report",
        json={
            "zone_id": "mathare",
            "observed_condition": "Street flooding",
            "perceived_severity": "Serious",
        },
    )
    assert resp.status_code == 201


def test_get_alerts_requires_auth():
    resp = client.get("/alerts")
    assert resp.status_code == 401


def test_get_alerts_with_auth(officer_token):
    resp = client.get("/alerts", headers={"Authorization": f"Bearer {officer_token}"})
    assert resp.status_code == 200


def test_acknowledge_alert(officer_token):
    resp = client.post("/alerts/1/acknowledge", headers={"Authorization": f"Bearer {officer_token}"})
    assert resp.status_code in (200, 400, 404)
    if resp.status_code == 200:
        assert resp.json()["acknowledged_status"] is True


def test_admin_get_users_requires_admin(officer_token):
    resp = client.get("/admin/users", headers={"Authorization": f"Bearer {officer_token}"})
    assert resp.status_code == 403


def test_admin_get_users_as_admin(admin_token):
    resp = client.get("/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
