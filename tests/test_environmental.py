"""QC, source-bin semantics, persistence and authorization; isolated fixture DB only."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
import math
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from src.api.database import Base, get_db
from src.api.models.db_models import Zone, User, AlertNotification
from src.api.models.environmental import EnvironmentalBase, EnvironmentalSource, EnvironmentalDataset, EnvironmentalObservation, EnvironmentalIngestion
from src.api.models.environmental_schemas import HistoricalImport, WaterLevelProposal
from src.api.routers import environmental, auth
from src.api.services.environmental_service import EnvironmentalService, DataRejected, normalize_reading, prepare_rows
from src.api.utils.security import create_access_token, hash_password

DAY = date(2024, 5, 1)
END = datetime(2024, 5, 2, tzinfo=timezone.utc)


def request(source="chirps-zones", start=DAY, end=DAY):
    return HistoricalImport(source_id=source, start_date=start, end_date=end)


def frame():
    return pd.DataFrame({"zone_id": ["a", "b"], "date": [DAY.isoformat()]*2, "precipitation": [0., 25.]})


class FixtureService(EnvironmentalService):
    def __init__(self):
        super().__init__("unused-fixture")
        self.frame = frame()

    def read_source(self, source_id):
        return self.frame.copy(), "a"*64, {"fixture": True, "bin_timezone": "UTC", "data_available_at": None}


@pytest.fixture
def env_api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    assert "environmental_datasets" not in inspect(engine).get_table_names()
    EnvironmentalBase.metadata.create_all(engine)
    db = Session(engine)
    db.add_all([Zone(id=z, name=z, sub_county="fixture", latitude=-1.2, longitude=36.8) for z in ("a", "b")])
    db.add_all([User(name=r, email=f"{r}@example.test", password_hash="unused", role=r, status="Active") for r in ("admin", "officer", "unapproved")])
    db.commit()
    service = FixtureService()
    app = FastAPI()
    app.include_router(environmental.router)
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[environmental.get_environmental_service] = lambda: service
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=db, service=service, engine=engine)
    db.close()
    engine.dispose()


def headers(role="admin"):
    return {"Authorization": "Bearer "+create_access_token({"sub": f"{role}@example.test"})}


@pytest.mark.parametrize("value,unit,wanted,flag", [(0.,"mm",0.,None),(2.,"cm",20.,None),(.1,"m",100.,None),
    (None,"mm",None,"MISSING_VALUE"),(float("nan"),"mm",None,"MISSING_VALUE"),(float("inf"),"mm",None,"INVALID_NUMBER"),
    (True,"mm",None,"INVALID_NUMBER"),("2","mm",None,"INVALID_NUMBER"),(-1.,"mm",None,"PHYSICAL_RANGE_ERROR"),
    (110.,"mm",110.,"REVIEW_LARGE_RAINFALL"),(1.,"inch",None,"UNSUPPORTED_UNIT"),(1e308,"m",None,"INVALID_NUMBER")])
def test_rain_qc(value, unit, wanted, flag):
    result, canonical, flags = normalize_reading("rainfall", value, unit)
    assert result == wanted and canonical == "mm"
    assert flags == ([flag] if flag else [])


@pytest.mark.parametrize("variable,value,unit,wanted", [("humidity",101,"%",None),("soil_moisture",-.1,"m3/m3",None),
    ("wind_speed",2,"m/s",7.2),("temperature",-10,"C",-10.)])
def test_other_units_and_physical_limits(variable,value,unit,wanted):
    assert normalize_reading(variable,value,unit)[0] == wanted


def test_gaps_flag_without_rows_or_zero_imputation():
    rows,count,metadata = prepare_rows(frame(),"chirps-zones",DAY,DAY+timedelta(days=1),{"a","b"})
    assert count == 2 and len(rows) == 2 and metadata["missing_source_bins"] == 2
    assert metadata["quality_flags"] == ["TIMESTAMP_GAPS"]
    assert rows[0]["value"] == 0. and rows[0]["data_available_at"] is None
    assert rows[0]["observed_at"].tzinfo is not None


@pytest.mark.parametrize("mutation,code", [
    (lambda f: pd.concat([f,f]),"DUPLICATE_ZONE_TIME"),
    (lambda f: f.assign(zone_id="unknown"),"UNKNOWN_OR_MISSING_ZONE"),
    (lambda f: f.assign(date="2024-05-01T01:00:00"),"OFF_GRID_TIMESTAMP"),
    (lambda f: f.assign(date="garbage"),"INVALID_SOURCE_TIMESTAMP"),
    (lambda f: f.assign(date=None),"INVALID_SOURCE_TIMESTAMP"),
    (lambda f: f.drop(columns="precipitation"),"MISSING_SOURCE_COLUMNS")])
def test_invalid_source_rejected(mutation,code):
    with pytest.raises(DataRejected,match=code):
        prepare_rows(mutation(frame()),"chirps-zones",DAY,DAY,{"a","b"})


def test_hourly_nairobi_bins_normalize_to_utc():
    f = pd.DataFrame({"zone_id":["a"],"time":["2024-05-01T00:00"],"precipitation":[1.],
        "temperature_2m":[20.],"relative_humidity_2m":[80.],"wind_speed_10m":[2.],"soil_moisture_0_to_7cm":[.4]})
    rows,_,_ = prepare_rows(f,"era5-hourly-cbd",DAY,DAY,{"a"})
    assert len(rows) == 5 and rows[0]["observed_at"] == END-timedelta(hours=27)
    assert "REANALYSIS_NOT_GROUND_SENSOR" in rows[0]["quality_flags"]


def test_import_replay_immutable_and_rainfall_zero_is_available(env_api):
    api=env_api
    first=api.service.ingest(api.db,request())
    identity=first["dataset"].id
    assert first["attempt"].status == "SUCCEEDED"
    assert api.service.ingest(api.db,request())["attempt"].status == "REUSED"
    assert api.db.query(EnvironmentalDataset).count()==1 and api.db.query(EnvironmentalObservation).count()==2
    assert api.db.query(EnvironmentalIngestion).count()==2 and api.db.query(AlertNotification).count()==0
    body=api.service.rainfall(api.db,identity,"a",END,24)
    assert body["rainfall_mm"]==0. and body["status"]=="AVAILABLE_HISTORICAL"
    body=api.service.rainfall(api.db,identity,"a",END,24,END)
    assert body["rainfall_mm"] is None and "SOURCE_AVAILABILITY_UNKNOWN_AT_ISSUE_TIME" in body["reason_codes"]
    assert not body["supports_operational_issue"]


def test_missing_null_window_and_late_availability_are_insufficient(env_api):
    api=env_api
    api.service.frame.loc[0,"precipitation"]=float("nan")
    dataset=api.service.ingest(api.db,request())["dataset"]
    assert dataset.qc_summary["missing_or_invalid_values"]==1
    result=api.service.rainfall(api.db,dataset.id,"a",END,24)
    assert result["rainfall_mm"] is None and "MISSING_OR_INVALID_RAINFALL" in result["reason_codes"]
    row=api.db.query(EnvironmentalObservation).filter_by(zone_id="b").one()
    row.data_available_at=END+timedelta(hours=1)
    api.db.commit()
    result=api.service.rainfall(api.db,dataset.id,"b",END,24,END)
    assert "SOURCE_AVAILABLE_AFTER_ISSUE_TIME" in result["reason_codes"]
    assert api.service.rainfall(api.db,dataset.id,"a",END,3)["rainfall_mm"] is None
    assert api.service.rainfall(api.db,dataset.id,"a",END+timedelta(days=1),24)["rainfall_mm"] is None


def test_rejected_import_has_audit_and_no_partial_dataset(env_api):
    api=env_api
    api.service.frame=pd.concat([frame(),frame()])
    result=api.service.ingest(api.db,request())
    assert result["dataset"] is None and result["attempt"].error_code=="DUPLICATE_ZONE_TIME"
    assert result["attempt"].status=="REJECTED" and result["attempt"].completed_at
    assert api.db.query(EnvironmentalDataset).count()==0 and api.db.query(EnvironmentalSource).count()==0


def test_partial_write_unexpected_failure_rolls_back_and_logs(env_api):
    api=env_api
    def fail(conn,cursor,statement,params,context,many):
        if statement.startswith("INSERT INTO environmental_observations"):
            raise RuntimeError("private-fixture-message-must-not-be-logged")
    event.listen(api.engine,"before_cursor_execute",fail)
    try:
        with pytest.raises(RuntimeError):
            api.service.ingest(api.db,request())
    finally:
        event.remove(api.engine,"before_cursor_execute",fail)
    assert api.db.query(EnvironmentalDataset).count()==0 and api.db.query(EnvironmentalObservation).count()==0
    row=api.db.query(EnvironmentalIngestion).one()
    assert row.status=="FAILED" and row.error_code=="PROCESSING_FAILED"


def test_static_has_no_fabricated_observation_dates(env_api):
    api=env_api
    api.service.frame=pd.DataFrame([{"zone_id":"a","slope_degrees":3.,"ndvi":.3,"impervious_fraction":.2,"vegetation_fraction":.6}])
    dataset=api.service.ingest(api.db,request("terrain-static"))["dataset"]
    assert dataset.start_at is None and dataset.end_at is None and dataset.observation_count==0
    assert dataset.provenance["extraction_verified"] is False
    assert api.service.ingest(api.db,request("terrain-static",date(2020,1,1),date(2020,1,1)))["dataset"].id==dataset.id


def test_real_auth_permissions_pagination_utc_and_disabled_contract(env_api):
    c=env_api.client
    path="/api/v1/environmental-data"
    for suffix in ("", "/sources", "/observations?dataset_id=x&zone_id=a", "/ingestions", "/water-levels", "/hydrology-status"):
        assert c.get(path+suffix).status_code==401
        assert c.get(path+suffix,headers=headers("unapproved")).status_code==403
    payload=request().model_dump(mode="json")
    assert c.post(path,json=payload,headers=headers("officer")).status_code==403
    response=c.post(path,json=payload,headers=headers())
    assert response.status_code==200,response.text
    dataset=response.json()["dataset"]
    assert dataset["start_at"].endswith("+00:00") and dataset["freshness"]["status"]=="HISTORICAL_ONLY"
    assert dataset["freshness"]["age_hours"]>24
    listing=c.get(path+"?limit=1",headers=headers("officer")).json()
    assert listing["total"]==1 and len(listing["items"])==1
    listing=c.get(path+f'/observations?dataset_id={dataset["id"]}&zone_id=a&limit=1',headers=headers("officer")).json()
    assert listing["items"][0]["value"]==0. and listing["items"][0]["observed_at"].endswith("+00:00")
    assert c.get(path+"?limit=201",headers=headers()).status_code==422
    assert c.get(path+f'/rainfall?dataset_id={dataset["id"]}&zone_id=a&end_at=2024-05-02&window_hours=24',headers=headers()).status_code==422
    assert c.get(path+"/water-levels",headers=headers()).json()["observations"]==[]
    water={"sensor_id":"fixture","zone_id":"a","observed_at":"2024-05-01T00:00:00Z",
        "data_available_at":"2024-05-01T00:01:00Z","water_level_m":1.,"unit":"m","vertical_datum":"fixture-only","source_reference":"fixture-only"}
    assert c.post(path+"/water-levels",json=water,headers=headers()).status_code==501
    assert c.post(path+"/water-levels",json=water,headers=headers("officer")).status_code==403
    assert c.get("/api/v1/geospatial/inundation-status").json()["predicted_depth_m"] is None
    user=env_api.db.query(User).filter_by(role="officer").one()
    user.status="Inactive"
    env_api.db.commit()
    assert c.get(path,headers=headers("officer")).status_code==401
    assert c.post("/auth/login",json={"email":user.email,"password":"fixture"}).status_code==401


@pytest.mark.parametrize("changes",[{"unit":"cm"},{"water_level_m":"1"},{"observed_at":"2024-05-01T00:00:00"},
    {"data_available_at":"2024-04-01T00:00:00Z"},{"water_level_m":float("nan")},{"extra":"denied"}])
def test_water_schema_proposal_rejects_unverified_payload_shapes(changes):
    with pytest.raises(ValidationError):
        WaterLevelProposal(**({"sensor_id":"fixture","zone_id":"a","observed_at":"2024-05-01T00:00:00Z",
            "data_available_at":"2024-05-01T00:01:00Z","water_level_m":1.,"unit":"m",
            "vertical_datum":"fixture","source_reference":"fixture"}|changes))


def test_source_hash_failure_rejected_and_paths_not_exposed(env_api):
    service=EnvironmentalService("private/nonexistent")
    result=service.ingest(env_api.db,request())
    assert result["attempt"].status=="REJECTED" and result["attempt"].error_code=="SOURCE_VALIDATION_FAILED"
    assert "private" not in str(result["attempt"].summary)


def test_versioned_openapi_and_rejected_requests_do_not_store_readings(env_api):
    schema=env_api.client.get('/openapi.json').json()
    assert schema['components']['schemas']['WaterLevelProposal']['additionalProperties'] is False
    assert '501' in schema['paths']['/api/v1/environmental-data/water-levels']['post']['responses']
    for changes in [{'source_id':'arbitrary-feed'},{'start_date':'2025-05-01'},{'end_date':'2026-05-01'}]:
        body=request().model_dump(mode='json')|changes
        assert env_api.client.post('/api/v1/environmental-data',json=body,headers=headers()).status_code==422
    assert env_api.db.query(EnvironmentalIngestion).count()==0


def test_postgres_schema_guard_rejects_non_postgres(env_api):
    from src.scripts.migrate_environmental import require_schema
    with env_api.engine.connect() as conn, pytest.raises(ValueError):
        require_schema(conn,"public")


def test_all_pinned_sources_have_real_parseable_provenance():
    from src.api.config import settings
    service=EnvironmentalService(settings.MODEL_V1_DATA_DIR)
    if not service.data_dir.exists():
        pytest.skip("Local ignored verified source package not installed")
    from src.api.services.environmental_service import SOURCES
    for source_id in SOURCES:
        f,checksum,metadata=service.read_source(source_id)
        assert len(checksum)==64 and metadata["data_available_at"] is None
        rows,count,extra=prepare_rows(f,source_id,DAY,DAY,set(f.zone_id))
        assert count>0
        if source_id=="terrain-static":
            assert rows==[] and not extra["extraction_verified"]
        else:
            assert rows and all(r["data_available_at"] is None for r in rows)
