"""Citizens report under the 17 Nairobi sub-counties (the OSM outlines on the map)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.database import Base, get_db
from src.api.models.db_models import CitizenReport, Zone
from src.api.routers.reports import router
from src.api.services import reporting_areas

KIBRA, LANGATA = "nairobi-subcounty-kibra", "nairobi-subcounty-langata"
STRATHMORE = dict(latitude=-1.310944, longitude=36.817167)   # Langata
GATWEKERA = dict(latitude=-1.315111, longitude=36.782472)    # Kibra


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Zone(id="mathare", name="Mathare", sub_county="Starehe", latitude=-1.26, longitude=36.86))
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client, db
    db.close()
    engine.dispose()


def payload(**changes):
    return {"observed_condition": "Street flooding", "perceived_severity": "Serious",
            "location_description": "Fixture landmark", **changes}


def test_all_seventeen_sub_counties_are_offered_by_name():
    names = [a["name"] for a in reporting_areas.areas()]
    assert len(names) == 17 and names == sorted(names)
    assert {"Kibra", "Langata", "Embakasi West", "Roysambu", "Makadara", "Kamukunji", "Dagoretti South"} <= set(names)


def test_pins_resolve_to_the_sub_county_that_contains_them():
    assert reporting_areas.locate(**STRATHMORE)["id"] == LANGATA
    assert reporting_areas.locate(**GATWEKERA)["id"] == KIBRA
    assert reporting_areas.locate(latitude=-1.26, longitude=36.86)["id"] == "nairobi-subcounty-ruaraka"
    assert reporting_areas.locate(latitude=-0.5, longitude=37.0) is None   # outside Nairobi


def test_list_and_locate_endpoints(api):
    client, _ = api
    listed = client.get("/reporting-areas")
    assert listed.status_code == 200 and len(listed.json()) == 17
    assert client.post("/reporting-areas/locate", json=STRATHMORE).json() == {"id": LANGATA, "name": "Langata"}
    assert client.post("/reporting-areas/locate", json={"latitude": -0.5, "longitude": 37.0}).json() is None
    assert client.post("/reporting-areas/locate", json={"latitude": 91, "longitude": 0}).status_code == 422
    assert client.get("/reporting-areas/locate?latitude=-1.3&longitude=36.8").status_code == 405  # never in a URL


def test_report_under_a_sub_county_is_saved_and_named(api):
    client, db = api
    response = client.post("/citizen-report", json=payload(area_id=KIBRA))
    assert response.status_code == 201
    body = response.json()
    assert body["area_id"] == KIBRA and body["zone_id"] is None
    saved = db.query(CitizenReport).one()
    assert saved.area_id == KIBRA and saved.zone_name == "Kibra"


def test_a_pin_alone_fills_in_its_sub_county(api):
    client, _ = api
    response = client.post("/citizen-report", json=payload(**STRATHMORE))
    assert response.status_code == 201 and response.json()["area_id"] == LANGATA


def test_a_pin_in_another_sub_county_is_explained_in_words(api):
    client, db = api
    response = client.post("/citizen-report", json=payload(area_id=KIBRA, **STRATHMORE))
    assert response.status_code == 422
    assert response.json()["detail"].startswith("The pin is in Langata, not Kibra")
    assert db.query(CitizenReport).count() == 0


@pytest.mark.parametrize("changes,status", [
    (dict(area_id="nairobi-subcounty-atlantis"), 404),
    (dict(latitude=-0.5, longitude=37.0), 422),           # pin outside Nairobi
    (dict(area_id=KIBRA, zone_id="mathare"), 422),        # one or the other
    (dict(), 422),                                        # neither area, zone nor pin
])
def test_invalid_area_choices_are_refused(api, changes, status):
    client, db = api
    assert client.post("/citizen-report", json=payload(**changes)).status_code == status
    assert db.query(CitizenReport).count() == 0


def test_older_clients_can_still_use_the_original_zones(api):
    client, db = api
    response = client.post("/citizen-report", json=payload(zone_id="mathare"))
    assert response.status_code == 201 and response.json()["zone_name"] == "Mathare"
    assert db.query(CitizenReport).one().area_id is None


def test_a_changed_outline_file_is_refused(monkeypatch, tmp_path):
    changed = tmp_path / "subcounties.geojson"
    changed.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(reporting_areas, "DEFAULT_SUBCOUNTY_PATH", changed)
    reporting_areas._areas.cache_clear()
    try:
        with pytest.raises(reporting_areas.ReportingAreasUnavailable):
            reporting_areas.areas()
    finally:
        monkeypatch.undo()
        reporting_areas._areas.cache_clear()
