"""Isolated research API/persistence/auth tests; no configured application records."""
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.database import Base, get_db
from src.api.models.db_models import AlertNotification, FloodPrediction, User, Zone
from src.api.models.proxy_v1 import ProxyPredictionV1, ProxyRunV1, ProxyV1Base, ZoneTerrainV1
from src.api.models.proxy_v1_schemas import ProxyRunRequest, ProxyRunResponse
from src.api.routers import auth, proxy_v1
from src.api.services.proxy_v1_service import ProxyV1Service, digest
from src.api.utils.security import create_access_token
from src.modeling.v1.contract import CLASS_NAMES, FEATURE_COLUMNS, MODEL_VERSION, V1ArtifactError

INPUT_DATE = date(2024, 4, 30)
ISSUED_AT = datetime(2024, 4, 30, 21, tzinfo=timezone.utc)


class FixtureModel:
    def __init__(self, loaded=True):
        self.loaded = loaded
        self.batches = []

    def info(self):
        return {"model_version": MODEL_VERSION, "model_task_type": "next_day_proxy_risk", "loaded": self.loaded,
                "status": "AVAILABLE" if self.loaded else "MODEL_UNAVAILABLE", "artifact_hash": "a" * 64,
                "feature_count": 20, "classes": list(CLASS_NAMES), "runtime": {"fixture": True},
                "evaluation": {"test_target_dates": ["2024-01-01", "2025-12-31"], "rows": 5848,
                               "metrics": {"accuracy": .8117305061559508}, "per_class": []}}

    def predict_many(self, rows):
        self.batches.append(rows)
        result = []
        for row in rows:
            index = 1 if row["chirps_daily_rain_mm"] < 10 else 2
            scores = [.1, .1, .1, .1]
            scores[index] = .7
            result.append({"risk_class": index, "risk_level": CLASS_NAMES[index], "model_class_score": .7,
                           "proxy_class_scores": dict(zip(CLASS_NAMES, scores))})
        return result


class FixtureBuilder:
    def __init__(self):
        self.missing_terrain = set()
        self.status_by_zone = {}
        self.identical = False
        self.calls = []

    def terrain_records(self):
        return [{"zone_id": zone, "terrain_version": "b" * 64,
                 "values": {"slope_degrees": 3.0, "ndvi": .4, "impervious_fraction": .2, "vegetation_fraction": .6},
                 "provenance": {"source_sha256": "b" * 64, "source_file": "synthetic-fixture.csv",
                                "ndvi_source_year": 2023, "land_cover_source_year": 2021}}
                for zone in ("a", "b") if zone not in self.missing_terrain]

    def build(self, zone_id, input_date, issued_at, terrain, mode="historical_replay"):
        self.calls.append((zone_id, input_date, issued_at, terrain, mode))
        status = self.status_by_zone.get(zone_id, "SUCCESS" if terrain is not None else "INSUFFICIENT_DATA")
        features = {name: 0.0 for name in FEATURE_COLUMNS}
        features.update(chirps_daily_rain_mm=5.0 if zone_id == "a" or self.identical else 15.0,
                        season_cos=1.0, slope_degrees=3.0, ndvi=.4, impervious_fraction=.2, vegetation_fraction=.6)
        return SimpleNamespace(status=status, features=features if status == "SUCCESS" else None,
                               reason_codes=[] if status == "SUCCESS" else ["MISSING_TERRAIN" if terrain is None else "SOURCE_STALE"],
                               source_metadata={"fixture": True, "source_released_at": None}, limitation_flags=["SYNTHETIC_TEST_FIXTURE"],
                               data_as_of=issued_at, feature_hash=digest(features) if status == "SUCCESS" else None)


@pytest.fixture
def v1_api(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    assert not any(name.startswith("proxy_v1_") for name in inspect(engine).get_table_names())
    ProxyV1Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([Zone(id=zone, name=f"Fixture {zone}", sub_county="fixture", latitude=-1.2, longitude=36.8) for zone in ("a", "b")])
    db.add_all([User(name="Fixture admin", email="admin@example.test", password_hash="unused", role="admin", status="Active"),
                User(name="Fixture officer", email="officer@example.test", password_hash="unused", role="officer", status="Active")])
    db.add(FloodPrediction(zone_id="a", timestamp=datetime.now(timezone.utc), risk_class=0, risk_level="Low", model_version="legacy_fixture"))
    db.commit()
    model, builder = FixtureModel(), FixtureBuilder()
    service = ProxyV1Service(model=model, builder=builder, data_dir=tmp_path)
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.include_router(proxy_v1.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[proxy_v1.get_proxy_service] = lambda: service
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=db, service=service, model=model, builder=builder, app=app, root=tmp_path)
    db.close()
    engine.dispose()


def payload(**changes):
    return {"mode": "historical_replay", "input_date": INPUT_DATE.isoformat(), "issued_at": ISSUED_AT.isoformat(), **changes}


def token(role="admin"):
    return {"Authorization": f"Bearer {create_access_token({'sub': role + '@example.test'})}"}


def run(api, **changes):
    return api.client.post("/api/v1/predictions/run", json=payload(**changes), headers=token())


def test_model_metadata_and_live_dashboard_never_reuse_legacy_scores(v1_api):
    api = v1_api
    model = api.client.get("/api/v1/model")
    assert model.status_code == 200 and model.json()["classes"] == list(CLASS_NAMES)
    assert model.json()["operational_status"] == "INSUFFICIENT_DATA"
    body = api.client.get("/api/v1/dashboard").json()
    assert body["mode"] == "live" and body["status"] == "INSUFFICIENT_DATA" and body["blockers"]
    assert len(body["zones"]) == 2
    assert all(z["risk_level"] == "Unknown" and z["model_class_score"] is None and z["proxy_class_scores"] is None for z in body["zones"])
    assert all(z["flood_probability"] is None and z["flood_probability_reason"] == "NOT_CALIBRATED_TO_OBSERVED_FLOODS" for z in body["zones"])
    assert api.model.batches == [] and api.builder.calls == []


def test_run_requires_real_admin_authentication(v1_api):
    client = v1_api.client
    assert client.post("/api/v1/predictions/run", json=payload()).status_code == 401
    assert client.post("/api/v1/predictions/run", json=payload(), headers=token("officer")).status_code == 403
    invalid = {"Authorization": "Bearer invalid-fixture-jwt"}
    assert client.post("/api/v1/predictions/run", json=payload(), headers=invalid).status_code == 401
    assert v1_api.db.query(ProxyRunV1).count() == 0


def test_distinct_zone_inputs_have_independently_computed_records_and_no_alerts(v1_api):
    response = run(v1_api)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS" and body["forecast_target_date"] == "2024-05-01"
    assert [item["risk_level"] for item in body["zones"]] == ["Moderate", "High"]
    assert [call[0] for call in v1_api.builder.calls] == ["a", "b"]
    assert len(v1_api.model.batches) == 1 and len(v1_api.model.batches[0]) == 2
    assert v1_api.db.query(ProxyPredictionV1).count() == 2
    assert v1_api.db.query(ZoneTerrainV1).count() == 2
    assert v1_api.db.query(FloodPrediction).count() == 1 and v1_api.db.query(AlertNotification).count() == 0
    for row in body["zones"]:
        assert row["freshness"] == "HISTORICAL_REPLAY" and row["model_artifact_hash"] == "a" * 64
        assert row["flood_probability"] is None and row["emergency_alert_delivery_enabled"] is False


def test_identical_inputs_have_equal_scores_and_distinct_zone_records(v1_api):
    v1_api.builder.identical = True
    body = run(v1_api).json()
    assert body["zones"][0]["proxy_class_scores"] == body["zones"][1]["proxy_class_scores"]
    assert body["zones"][0]["feature_hash"] == body["zones"][1]["feature_hash"]
    assert [z["zone"]["id"] for z in body["zones"]] == ["a", "b"]


def test_idempotent_rerun_preserves_original_execution_and_rejects_changed_payload(v1_api):
    first = run(v1_api, idempotency_key="fixture-run").json()
    again = run(v1_api, idempotency_key="fixture-run").json()
    assert again["idempotent_replay"] is True
    assert again["run_id"] == first["run_id"] and again["executed_at"] == first["executed_at"]
    assert len(v1_api.model.batches) == 1 and v1_api.db.query(ProxyRunV1).count() == 1
    assert run(v1_api, idempotency_key="fixture-run", zone_ids=["a"]).status_code == 409
    (v1_api.root / "changed_source.json").write_text('{}')
    assert run(v1_api, idempotency_key="fixture-run").status_code == 409


def test_reinstall_timestamp_does_not_change_source_identity(v1_api):
    import json
    path = v1_api.root / "source_manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "imported_at": "2026-11-06T00:00:00Z", "recipe_notebook_sha256": "f" * 64}))
    original = v1_api.service.source_identity()
    path.write_text(json.dumps({"schema_version": 1, "imported_at": "2026-11-07T00:00:00Z", "recipe_notebook_sha256": "f" * 64}))
    assert v1_api.service.source_identity() == original
    path.write_text(json.dumps({"schema_version": 1, "imported_at": "2026-11-07T00:00:00Z", "recipe_notebook_sha256": "e" * 64}))
    assert v1_api.service.source_identity() != original


def test_identical_run_cannot_silently_register_an_untracked_key_alias(v1_api):
    original = run(v1_api, idempotency_key="original-key")
    assert original.status_code == 200
    assert run(v1_api, idempotency_key="different-key").status_code == 409
    assert run(v1_api).json()["run_id"] == original.json()["run_id"]
    assert v1_api.db.query(ProxyRunV1).count() == 1


def test_last_representable_day_is_rejected_before_date_arithmetic(v1_api):
    assert v1_api.client.get("/api/v1/dashboard?mode=historical_replay&input_date=9999-12-31").status_code == 422
    assert run(v1_api, input_date="9999-12-31", issued_at="9999-12-31T23:00:00+03:00").status_code == 422
    assert v1_api.db.query(ProxyRunV1).count() == 0


def test_missing_zone_terrain_does_not_copy_another_zone_prediction(v1_api):
    v1_api.builder.missing_terrain.add("b")
    body = run(v1_api).json()
    assert body["status"] == "PARTIAL"
    assert body["zones"][0]["status"] == "SUCCESS"
    missing = body["zones"][1]
    assert missing["status"] == "INSUFFICIENT_DATA" and "MISSING_TERRAIN" in missing["reason_codes"]
    assert missing["risk_level"] == "Unknown" and missing["proxy_class_scores"] is None
    assert len(v1_api.model.batches[0]) == 1


def test_stale_zone_and_model_failure_are_persisted_without_scores(v1_api):
    v1_api.builder.status_by_zone["a"] = "STALE_DATA"
    v1_api.model.loaded = False
    body = run(v1_api).json()
    assert body["status"] == "MODEL_UNAVAILABLE"
    assert [row["status"] for row in body["zones"]] == ["STALE_DATA", "MODEL_UNAVAILABLE"]
    assert body["zones"][0]["freshness"] == "STALE"
    assert all(row["risk_class"] is None and row["proxy_class_scores"] is None for row in body["zones"])


def test_live_run_persists_only_explicit_unavailable_statuses(v1_api):
    body = run(v1_api, mode="live").json()
    assert body["status"] == "INSUFFICIENT_DATA"
    assert v1_api.db.query(ProxyPredictionV1).count() == 2
    assert all(row["risk_level"] == "Unknown" and row["proxy_class_scores"] is None for row in body["zones"])
    assert v1_api.builder.calls == [] and v1_api.model.batches == []


def test_unexpected_native_inference_failure_is_persisted_as_failed(v1_api, monkeypatch):
    monkeypatch.setattr(v1_api.model, "predict_many", Mock(side_effect=RuntimeError("unexpected fixture failure")))
    response = run(v1_api)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FAILED" and v1_api.db.query(ProxyRunV1).one().status == "FAILED"
    assert all(row["status"] == "FAILED" and row["risk_class"] is None for row in body["zones"])
    assert body["blockers"] == ["UNEXPECTED_MODEL_INFERENCE_FAILURE"]


def test_failed_commit_rolls_back_run_results_and_new_terrain(v1_api, monkeypatch):
    monkeypatch.setattr(v1_api.db, "commit", Mock(side_effect=SQLAlchemyError("simulated transaction failure")))
    response = run(v1_api)
    assert response.status_code == 503
    assert v1_api.db.query(ProxyRunV1).count() == 0
    assert v1_api.db.query(ProxyPredictionV1).count() == 0
    assert v1_api.db.query(ZoneTerrainV1).count() == 0
    assert v1_api.db.query(FloodPrediction).count() == 1


def test_history_filters_and_explicit_replay_date_never_fall_back(v1_api):
    first = run(v1_api, zone_ids=["a"]).json()
    history = v1_api.client.get("/api/v1/predictions?zone_id=a&input_date=2024-04-30&forecast_target_date=2024-05-01&mode=historical_replay")
    assert history.status_code == 200 and history.json()["total"] == 1
    assert history.json()["items"][0]["run_id"] == first["run_id"]
    assert v1_api.client.get("/api/v1/predictions?zone_id=b").json()["total"] == 0
    selected = v1_api.client.get("/api/v1/dashboard?mode=historical_replay&input_date=2024-04-30").json()
    assert selected["status"] == "PARTIAL"
    assert selected["zones"][1]["reason_codes"] == ["ZONE_NOT_IN_SELECTED_REPLAY"]
    empty = v1_api.client.get("/api/v1/dashboard?mode=historical_replay&input_date=2024-05-01").json()
    assert all(row["risk_level"] == "Unknown" for row in empty["zones"])
    assert v1_api.client.get("/api/v1/dashboard?mode=historical_replay").status_code == 422


@pytest.mark.parametrize("changes", [
    {"issued_at": "2024-05-01T00:00:00"}, {"issued_at": "2024-04-30T20:59:00+00:00"},
    {"mode": "training"}, {"zone_ids": ["a", "a"]}, {"input_date": "not-a-date"},
    {"source_path": "unapproved-file.csv"}, {"features": {"rain": 0}},
])
def test_invalid_run_context_and_unapproved_inputs_are_rejected(v1_api, changes):
    assert run(v1_api, **changes).status_code == 422
    assert v1_api.db.query(ProxyRunV1).count() == 0


def test_unknown_zone_is_a_404_without_writes(v1_api):
    assert run(v1_api, zone_ids=["unknown-zone"]).status_code == 404
    assert v1_api.db.query(ProxyRunV1).count() == 0


def test_storage_errors_are_503_without_private_details(v1_api, monkeypatch):
    monkeypatch.setattr(v1_api.service, "history", Mock(side_effect=SQLAlchemyError("private server detail")))
    response = v1_api.client.get("/api/v1/predictions")
    assert response.status_code == 503 and "private server detail" not in response.text


def test_openapi_has_typed_null_probability_and_admin_security(v1_api):
    doc = v1_api.client.get("/openapi.json").json()
    operation = doc["paths"]["/api/v1/predictions/run"]["post"]
    assert operation["security"] == [{"OAuth2PasswordBearer": []}]
    assert "409" in operation["responses"] and "503" in operation["responses"]
    schema = doc["components"]["schemas"]["ProxyZoneResult"]
    assert schema["properties"]["flood_probability"]["type"] == "null"
    assert "forecast_target_date" in schema["required"]
    assert schema["properties"]["model_class_score"] != schema["properties"]["flood_probability"]


def test_default_api_lifespan_has_no_database_scheduler_or_weather_side_effects(monkeypatch):
    from src.api import main
    monkeypatch.setattr(main.settings, "AUTO_CREATE_LEGACY_TABLES", False)
    monkeypatch.setattr(main.settings, "LEGACY_SCHEDULER_ENABLED", False)
    create = Mock(side_effect=AssertionError("no schema mutation on startup"))
    connect = Mock(side_effect=AssertionError("no database connection on startup"))
    start = Mock(side_effect=AssertionError("no scheduler on startup"))
    provider = Mock(side_effect=AssertionError("no weather request on startup"))
    monkeypatch.setattr(main.Base.metadata, "create_all", create)
    monkeypatch.setattr(main.engine, "connect", connect)
    monkeypatch.setattr(main.scheduler, "start", start)
    monkeypatch.setattr(main.pipeline, "run", provider)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
    create.assert_not_called()
    connect.assert_not_called()
    start.assert_not_called()
    provider.assert_not_called()


def test_corrupt_legacy_artifact_does_not_break_api_module_import(monkeypatch):
    from src.api.services.ml_service import MLService
    monkeypatch.setattr("src.api.services.ml_service.joblib.load", Mock(side_effect=ValueError("corrupt fixture")))
    service = MLService()
    assert service.is_loaded is False


def test_real_historical_builder_runtime_and_persistence_replay(v1_api):
    from src.api.config import settings
    if not Path(settings.MODEL_V1_DIR).is_dir() or not Path(settings.MODEL_V1_DATA_DIR).is_dir() or not Path(settings.MODEL_V1_PYTHON).is_file():
        pytest.skip("Restore the pinned local research model/runtime/source bundle to run real replay integration")
    # Fixture zones are deliberately different from the actual dataset. Use two
    # explicit existing research zone IDs without altering application records.
    for zone_id in ("mathare", "kibera"):
        v1_api.db.add(Zone(id=zone_id, name=zone_id, sub_county="fixture", latitude=-1.2, longitude=36.8))
    v1_api.db.commit()
    service = ProxyV1Service()
    request = ProxyRunRequest(**payload(zone_ids=["mathare", "kibera"]))
    result = ProxyRunResponse.model_validate(service.run(v1_api.db, request)).model_dump(mode="json")
    assert result["status"] == "SUCCESS"
    assert {row["zone"]["id"] for row in result["zones"]} == {"mathare", "kibera"}
    assert all(row["mode"] == "historical_replay" and row["flood_probability"] is None for row in result["zones"])
    assert all(row["source_metadata"]["source_released_at"] for row in result["zones"])
    assert v1_api.db.query(AlertNotification).count() == 0
