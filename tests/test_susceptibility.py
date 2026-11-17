"""Local susceptibility: pinned, complete, and it separates places the forecast cannot."""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.services import susceptibility


def test_every_located_place_has_a_level_and_reasons():
    rows = susceptibility.by_area()
    assert len(rows) == 36
    assert {r["level"] for r in rows.values()} == {"Lower", "Medium", "Higher"}
    for r in rows.values():
        assert r["score"] == sum(f["points"] for f in r["factors"]) and len(r["factors"]) == 6


def test_it_separates_places_that_share_a_forecast_cell():
    rows = susceptibility.by_area()
    # Mukuru Kayaba sits ~1 m above the Ngong River; Kibera's Gatwekera Sokomoko ~36 m above the Motoine.
    assert rows["NFW-S013"]["level"] == "Higher" and rows["NFW-S013"]["height_above_river_m"] < 3
    assert rows["NFW-S021"]["level"] == "Lower"


def test_public_endpoint_and_integrity_check(monkeypatch, tmp_path):
    with TestClient(app) as client:
        response = client.get("/monitoring-areas/susceptibility")
    assert response.status_code == 200 and len(response.json()["rows"]) == 36
    changed = tmp_path / "s.json"
    changed.write_bytes(susceptibility.PATH.read_bytes() + b" ")
    monkeypatch.setattr(susceptibility, "PATH", changed)
    susceptibility.load.cache_clear()
    try:
        with pytest.raises(susceptibility.SusceptibilityUnavailable):
            susceptibility.load()
    finally:
        monkeypatch.undo()
        susceptibility.load.cache_clear()
