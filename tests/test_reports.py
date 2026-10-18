"""Citizen report contract tests using an isolated in-memory database.

Run from the project root: python -m pytest tests/test_reports.py -v
Uses the normal environment settings but never connects to the configured database.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.database import Base, get_db
from src.api.models.db_models import CitizenReport, Zone
from src.api.routers.reports import router


@pytest.fixture
def report_api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Zone(id="mathare", name="Mathare", sub_county="Starehe", latitude=-1.26, longitude=36.86))
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        db.close()
        engine.dispose()


def report_payload(**updates):
    return {
        "zone_id": "mathare", "observed_condition": "Street flooding",
        "perceived_severity": "Serious", "description": "  Water near the bridge  ",
        **updates,
    }


def test_anonymous_report_is_persisted_and_returns_confirmation(report_api):
    client, db = report_api
    response = client.post("/citizen-report", json=report_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["timestamp"]
    saved = db.query(CitizenReport).one()
    assert saved.id == body["id"]
    assert saved.zone_id == "mathare"
    assert saved.observed_condition == "Street flooding"
    assert saved.perceived_severity == "Serious"
    assert saved.description == "Water near the bridge"
    assert len(saved.ip_hash) == 64
    assert "ip_hash" not in body


@pytest.mark.parametrize("description", [None, "", "   "])
def test_description_is_optional_and_blank_values_are_normalized(report_api, description):
    client, db = report_api
    response = client.post("/citizen-report", json=report_payload(description=description))
    assert response.status_code == 201
    assert response.json()["description"] is None
    assert db.query(CitizenReport).one().description is None


@pytest.mark.parametrize("field,value", [
    ("zone_id", ""), ("zone_id", "   "), ("zone_id", "x" * 51),
    ("observed_condition", ""), ("observed_condition", "Flash flood"),
    ("perceived_severity", "High"), ("perceived_severity", ""),
    ("description", "x" * 201),
])
def test_invalid_reports_are_rejected_before_persistence(report_api, field, value):
    client, db = report_api
    response = client.post("/citizen-report", json=report_payload(**{field: value}))
    assert response.status_code == 422
    assert any(error["loc"][-1] == field for error in response.json()["detail"])
    assert db.query(CitizenReport).count() == 0


def test_description_at_the_limit_is_accepted(report_api):
    client, db = report_api
    response = client.post("/citizen-report", json=report_payload(description="x" * 200))
    assert response.status_code == 201
    assert len(db.query(CitizenReport).one().description) == 200


def test_unsupported_zone_does_not_create_a_report(report_api):
    client, db = report_api
    response = client.post("/citizen-report", json=report_payload(zone_id="Other"))
    assert response.status_code == 404
    assert db.query(CitizenReport).count() == 0


def test_failed_save_returns_an_error_and_rolls_back(report_api, monkeypatch):
    client, db = report_api

    def fail_commit():
        raise SQLAlchemyError("Simulated write failure")

    monkeypatch.setattr(db, "commit", fail_commit)
    response = client.post("/citizen-report", json=report_payload())
    assert response.status_code == 500
    assert response.json()["detail"] == "Database error occurred"
    assert db.query(CitizenReport).count() == 0
