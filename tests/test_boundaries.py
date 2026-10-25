"""Boundary validation/API tests plus opt-in native PostGIS integration tests."""
import copy
import hashlib
import json
import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.config import settings
from src.api.database import get_db
from src.api.routers import boundaries
from src.api.services.boundary_service import (
    DEFAULT_BOUNDARY_PATH,
    DEFAULT_SUBCOUNTY_PATH,
    get_boundaries,
    load_boundaries,
    validate_feature_collection,
)


def source_document():
    return json.loads(DEFAULT_BOUNDARY_PATH.read_text(encoding="utf-8"))


def test_packaged_boundary_matches_provenance_and_has_one_county():
    metadata = json.loads(DEFAULT_BOUNDARY_PATH.with_suffix(".source.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(DEFAULT_BOUNDARY_PATH.read_bytes()).hexdigest() == metadata["geojson_sha256"]
    features = validate_feature_collection(source_document())
    assert len(features) == 1
    assert features[0]["id"] == "nairobi-county"
    assert features[0]["properties"]["admin_level"] == 1
    assert features[0]["properties"]["country_code"] == "KEN"


@pytest.mark.parametrize("document", [None, {}, {"type": "FeatureCollection", "features": []}])
def test_rejects_missing_collections(document):
    with pytest.raises(ValueError):
        validate_feature_collection(document)


@pytest.mark.parametrize("change", [
    {"id": "../../boundary"}, {"properties": {}}, {"geometry": None},
    {"geometry": {"type": "Point", "coordinates": [36.8, -1.3]}},
    {"geometry": {"type": "Polygon", "coordinates": []}},
    {"geometry": {"type": "Polygon", "coordinates": [[[36, -1], [37, -1], [37, -2], [36, -2]]]}},
    {"geometry": {"type": "Polygon", "coordinates": [[[360000, -1], [37, -1], [37, -2], [360000, -1]]]}},
    {"geometry": {"type": "Polygon", "coordinates": [[[True, -1], [37, -1], [37, -2], [True, -1]]]}},
    {"geometry": {"type": "Polygon", "coordinates": [[[float("nan"), -1], [37, -1], [37, -2], [float("nan"), -1]]]}},
])
def test_rejects_malformed_or_non_geographic_boundaries(change):
    document = source_document()
    document["features"][0].update(change)
    with pytest.raises(ValueError):
        validate_feature_collection(document)


def test_rejects_ambiguous_ids_and_non_rfc7946_crs():
    document = source_document()
    document["features"].append(copy.deepcopy(document["features"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        validate_feature_collection(document)
    document = source_document()
    document["crs"] = {"type": "name", "properties": {"name": "EPSG:3857"}}
    with pytest.raises(ValueError, match="longitude/latitude"):
        validate_feature_collection(document)


def test_missing_spatial_setup_returns_503_instead_of_empty_boundaries():
    engine = create_engine("sqlite://")
    app = FastAPI()
    app.include_router(boundaries.router, prefix="/boundaries")
    with Session(engine) as db:
        app.dependency_overrides[get_db] = lambda: db
        response = TestClient(app).get("/boundaries")
    engine.dispose()
    assert response.status_code == 503
    assert "not been configured" in response.json()["detail"]


def test_query_errors_return_503_without_database_details(monkeypatch):
    def fail(*args):
        raise SQLAlchemyError("Private database detail")

    monkeypatch.setattr(boundaries, "get_boundaries", fail)
    app = FastAPI()
    app.include_router(boundaries.router, prefix="/boundaries")
    app.dependency_overrides[get_db] = lambda: None
    response = TestClient(app).get("/boundaries")
    assert response.status_code == 503
    assert "Private database detail" not in response.text


@pytest.fixture
def postgis_connection():
    if os.getenv("RUN_POSTGIS_TESTS") != "1":
        pytest.skip("Set RUN_POSTGIS_TESTS=1 to run native PostGIS tests in a temporary schema")
    engine = create_engine(os.getenv("POSTGIS_TEST_DATABASE_URL", settings.DATABASE_URL))
    schema = "test_boundaries_" + uuid4().hex
    with engine.begin() as setup:
        installed = setup.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")).scalar()
        assert installed, "Enable PostGIS with python -m src.scripts.load_boundaries first"
        setup.execute(text(f'CREATE SCHEMA "{schema}"'))
    connection = engine.connect()
    transaction = connection.begin()
    connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
    connection.execute(text("CREATE TABLE zones (id VARCHAR(50) PRIMARY KEY, latitude FLOAT NOT NULL, longitude FLOAT NOT NULL)"))
    try:
        yield connection
    finally:
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        # Only this fixture's UUID-named schema can be removed.
        assert schema.startswith("test_boundaries_") and len(schema) == 48
        with engine.begin() as cleanup:
            cleanup.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_native_geometry_srid_validity_spatial_index_and_coverage(postgis_connection):
    connection = postgis_connection
    load_boundaries(connection)
    row = connection.execute(text("""
        SELECT ST_GeometryType(geometry) AS type, ST_SRID(geometry) AS srid,
               ST_IsValid(geometry) AS valid, ST_IsEmpty(geometry) AS empty,
               ST_IsPolygonCCW(geometry) AS ccw,
               ST_Covers(geometry, ST_SetSRID(ST_MakePoint(36.817223, -1.286389),4326)) AS covers_city
        FROM administrative_boundaries
    """)).mappings().one()
    assert row == {"type": "ST_MultiPolygon", "srid": 4326, "valid": True, "empty": False, "ccw": True, "covers_city": True}
    indexes = connection.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema() AND tablename = 'administrative_boundaries'")).scalars()
    assert any("USING gist (geometry)" in definition for definition in indexes)


def test_reimport_updates_the_same_boundary_without_duplicates(postgis_connection, tmp_path):
    connection = postgis_connection
    load_boundaries(connection)
    document = source_document()
    document["features"][0]["properties"]["name"] = "Updated county label"
    path = tmp_path / "updated.geojson"
    path.write_text(json.dumps(document), encoding="utf-8")
    load_boundaries(connection, path)
    assert connection.execute(text("SELECT count(*) FROM administrative_boundaries")).scalar() == 1
    assert connection.execute(text("SELECT name FROM administrative_boundaries")).scalar() == "Updated county label"


def test_invalid_topology_rolls_back_the_entire_import(postgis_connection, tmp_path):
    connection = postgis_connection
    load_boundaries(connection)
    document = source_document()
    document["features"][0]["properties"]["name"] = "Must roll back"
    invalid = copy.deepcopy(document["features"][0])
    invalid["id"] = "self-intersection"
    invalid["geometry"] = {"type": "Polygon", "coordinates": [[[36, -1], [37, -2], [36, -2], [37, -1], [36, -1]]]}
    document["features"].append(invalid)
    path = tmp_path / "invalid.geojson"
    path.write_text(json.dumps(document), encoding="utf-8")
    savepoint = connection.begin_nested()
    with pytest.raises(IntegrityError):
        load_boundaries(connection, path)
    savepoint.rollback()
    assert connection.execute(text("SELECT name FROM administrative_boundaries")).scalar() == "Nairobi County"
    assert connection.execute(text("SELECT count(*) FROM administrative_boundaries")).scalar() == 1


def test_boundary_endpoints_return_geojson_and_404(postgis_connection):
    load_boundaries(postgis_connection)
    app = FastAPI()
    app.include_router(boundaries.router, prefix="/boundaries")
    with Session(bind=postgis_connection, join_transaction_mode="create_savepoint") as db:
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        response = client.get("/boundaries")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/geo+json"
        collection = response.json()
        assert collection["type"] == "FeatureCollection"
        assert len(collection["features"]) == 1
        feature = client.get("/boundaries/nairobi-county").json()
        assert feature == collection["features"][0]
        assert feature["geometry"]["type"] == "MultiPolygon"
        assert feature["properties"]["source_license"] == "Public Domain"
        assert "crs" not in feature["geometry"]
        assert client.get("/boundaries/missing").status_code == 404


def test_configured_but_empty_spatial_table_returns_empty_collection(postgis_connection):
    load_boundaries(postgis_connection)
    postgis_connection.execute(text("DELETE FROM administrative_boundaries"))
    with Session(bind=postgis_connection, join_transaction_mode="create_savepoint") as db:
        assert get_boundaries(db) == {"type": "FeatureCollection", "features": []}


def test_subcounty_extract_preserves_provenance_and_17_source_features():
    metadata = json.loads(DEFAULT_SUBCOUNTY_PATH.with_suffix(".source.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(DEFAULT_SUBCOUNTY_PATH.read_bytes()).hexdigest() == metadata["geojson_sha256"]
    features = validate_feature_collection(json.loads(DEFAULT_SUBCOUNTY_PATH.read_text(encoding="utf-8")))
    assert len(features) == 17
    assert all(feature["properties"]["admin_level"] == 2 for feature in features)
    assert {feature["properties"]["source_feature_id"] for feature in features} == {item["shapeID"] for item in metadata["selection"]}


def test_subcounty_monitoring_ids_use_point_location_not_labels(postgis_connection):
    connection = postgis_connection
    load_boundaries(connection)
    load_boundaries(connection, DEFAULT_SUBCOUNTY_PATH)
    connection.execute(text("""
        INSERT INTO zones (id, latitude, longitude) VALUES
        ('arbitrary-name', -1.26, 36.86), ('outside-county', 0, 0)
    """))
    with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
        features = get_boundaries(db)["features"]
    matches = [feature for feature in features if "arbitrary-name" in feature["properties"]["monitoring_zone_ids"]]
    assert len(matches) == 1
    assert matches[0]["properties"]["admin_level"] == 2
    assert matches[0]["properties"]["name"] == "Mathare"
    assert all("outside-county" not in feature["properties"]["monitoring_zone_ids"] for feature in features)
    assert next(feature for feature in features if feature["id"] == "nairobi-county")["properties"]["monitoring_zone_ids"] == []
