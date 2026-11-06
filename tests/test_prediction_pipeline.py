"""Pipeline and public coverage tests in an isolated SQLite database."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.database import Base, get_db
from src.api.models.db_models import AlertNotification, FloodPrediction, Zone
from src.api.routers.predictions import dashboard_router
from src.api.services import pipeline as pipeline_module
from src.api.services.model_contract import ModelInputError, PREDICTION_CONTEXT, SERVING_VERSION


@pytest.fixture
def isolated_pipeline(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add_all([Zone(id=name, name=name, sub_county="test", latitude=lat, longitude=lon)
                    for name, lat, lon in [("a", -1.26, 36.86), ("b", -1.32, 36.78)]])
        db.commit()
    factory = Mock(side_effect=sessions)
    model = SimpleNamespace(is_loaded=True, predict=Mock(return_value={
        "risk_class": 2, "risk_level": "High", "confidence": 0.8,
    }))
    weather = SimpleNamespace(
        get_current_weather=Mock(return_value={"timestamp": "2026-10-25T12:00:00+03:00"}),
        compute_features=Mock(return_value={"valid": "features"}),
    )
    monkeypatch.setattr(pipeline_module, "SessionLocal", factory)
    monkeypatch.setattr(pipeline_module, "ml_service", model)
    monkeypatch.setattr(pipeline_module, "weather_service", weather)
    try:
        yield pipeline_module.PredictionPipeline(), sessions, factory, model, weather
    finally:
        engine.dispose()


def test_shared_weather_is_inferred_once_and_saved_atomically_for_existing_zones(isolated_pipeline):
    pipeline, sessions, _, model, weather = isolated_pipeline
    summary = pipeline.run()
    assert summary["status"] == "success" and summary["zones_processed"] == 2
    assert summary["prediction_context"] == PREDICTION_CONTEXT
    assert summary["weather_timestamp"] == "2026-10-25T12:00:00+03:00"
    model.predict.assert_called_once_with(weather.compute_features.return_value)
    with sessions() as db:
        rows = db.query(FloodPrediction).all()
        assert {row.zone_id for row in rows} == {"a", "b"}
        assert {row.risk_level for row in rows} == {"High"}
        assert {row.model_version for row in rows} == {SERVING_VERSION}
        assert db.query(AlertNotification).count() == 2
    pipeline.run()
    with sessions() as db:
        assert db.query(AlertNotification).count() == 2  # Existing alert cooldown is preserved.


@pytest.mark.parametrize("failure", ["model_unavailable", "weather_fetch", "model_inputs"])
def test_missing_model_weather_or_features_cannot_create_predictions_or_alerts(isolated_pipeline, failure):
    pipeline, sessions, factory, model, weather = isolated_pipeline
    with sessions() as db:
        db.add(FloodPrediction(zone_id="a", timestamp=datetime.now(timezone.utc), risk_level="Low", risk_class=0))
        db.commit()
    if failure == "model_unavailable":
        model.is_loaded = False
    elif failure == "weather_fetch":
        weather.get_current_weather.return_value = None
    else:
        weather.compute_features.side_effect = ModelInputError("missing data")
    assert pipeline.run() == {"status": "failed", "reason": failure}
    factory.assert_not_called()
    model.predict.assert_not_called()
    with sessions() as db:
        assert db.query(FloodPrediction).count() == 1
        assert db.query(AlertNotification).count() == 0


def test_save_failure_rolls_back_all_zone_predictions_and_alerts(isolated_pipeline, monkeypatch):
    pipeline, sessions, _, _, _ = isolated_pipeline
    db = sessions()
    monkeypatch.setattr(db, "commit", Mock(side_effect=RuntimeError("simulated failure")))
    monkeypatch.setattr(pipeline_module, "SessionLocal", lambda: db)
    assert pipeline.run()["reason"] == "database_error"
    with sessions() as check:
        assert check.query(FloodPrediction).count() == check.query(AlertNotification).count() == 0


def test_unexpected_inference_error_is_reported_without_opening_a_database_session(isolated_pipeline):
    pipeline, _, factory, model, _ = isolated_pipeline
    model.predict.side_effect = RuntimeError("simulated incompatible model")
    assert pipeline.run()["reason"] == "inference_error"
    factory.assert_not_called()


def test_public_dashboard_exposes_scope_and_leaves_absent_predictions_unknown(isolated_pipeline):
    pipeline, sessions, _, _, _ = isolated_pipeline
    app = FastAPI()
    app.include_router(dashboard_router)
    def database():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = database
    client = TestClient(app)
    body = client.get("/dashboard").json()
    assert body["prediction_context"] == PREDICTION_CONTEXT
    assert body["last_updated"] is None and body["highest_risk"] == "Unknown"
    assert all(row["risk_level"] == "Unknown" and row["risk_class"] is None for row in body["zones"])
    pipeline.run()
    body = client.get("/dashboard").json()
    assert body["highest_risk"] == "High" and body["last_updated"]
    assert body["prediction_context"]["location_specific"] is False
