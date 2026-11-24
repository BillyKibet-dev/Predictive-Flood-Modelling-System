"""Collected rainfall: area-weighted, gaps stay gaps, grows as days are stored, staff only."""
from datetime import date
import csv
import io

import pytest

from src.api.services import imerg_early, observed_rainfall as observed
from src.api.utils.security import create_access_token
from tests.test_api import api, password_hash  # noqa: F401  (fixtures)

KIBRA = "nairobi-subcounty-kibra"


def token(role="officer"):
    return {"Authorization": "Bearer " + create_access_token({"sub": f"{role}@example.test"})}


def all_cells(mm, *, broken=()):
    cells = {}
    for i in range(imerg_early.LAT_INDEX[0], imerg_early.LAT_INDEX[1] + 1):
        for j in range(imerg_early.LON_INDEX[0], imerg_early.LON_INDEX[1] + 1):
            cid = imerg_early.cell_id(i, j)
            cells[cid] = dict(precipitation_mm=None if cid in broken else mm, complete=cid not in broken, sample_count=48)
    return cells


@pytest.fixture
def store(tmp_path):
    """A store with 1, 2 and 4 Nov collected (3 Nov missing); day 2 has one cell incomplete."""
    kibra_cell = next(iter(observed.weights()[KIBRA]))
    records = {date(2026, 11, 1): all_cells(10.0), date(2026, 11, 2): all_cells(4.0, broken={kibra_cell}),
               date(2026, 11, 4): all_cells(0.0)}
    (tmp_path / "days").mkdir()
    for day in records:
        (tmp_path / "days" / f"{day}.json").write_text("{}")
    reads = []

    def reader(day, root):
        reads.append(day)
        return dict(cells=records[day], received_at_utc=f"{day}T06:00:00+00:00", version="V07C")
    return tmp_path, reader, reads, kibra_cell


def test_weights_cover_every_sub_county_and_nairobi_is_their_union():
    weights = observed.weights()
    areas = [k for k in weights if k != observed.NAIROBI]
    assert len(areas) == 17, "every sub-county is covered by at least one satellite cell"
    total = sum(weights[observed.NAIROBI].values())
    assert total == sum(sum(v.values()) for k, v in weights.items() if k != observed.NAIROBI)
    assert 550 < total < 800, "about Nairobi's 696 km2 at ~1.2 km2 per sample"


def test_daily_values_are_area_weighted_and_gaps_stay_gaps(store):
    root, reader, reads, _ = store
    data = observed.summary(root=root, reader=reader)
    days = {d["date"]: d for d in data["daily"]}
    assert data["first_day"] == "2026-11-01" and data["last_day"] == "2026-11-04"
    assert data["days_stored"] == 3 and data["days_missing"] == 1, "3 Nov was never collected"
    assert days["2026-11-01"]["nairobi_mm"] == 10.0
    kibra = [a["id"] for a in data["areas"]].index(KIBRA)
    assert days["2026-11-02"]["by_area"][kibra] is None, "an incomplete covering cell is a gap, not zero"
    assert days["2026-11-02"]["nairobi_mm"] is None
    assert days["2026-11-04"]["nairobi_mm"] == 0.0
    assert data["monthly"] == [dict(month="2026-11", total_mm=10.0, days=2)]
    assert "2026-11-04T06" in data["last_received_at"]


def test_each_day_is_verified_once_then_new_days_appear(store):
    root, reader, reads, _ = store
    observed.summary(root=root, reader=reader)
    first = len(reads)
    observed.summary(root=root, reader=reader)
    assert len(reads) == first, "stored days are not re-read"
    (root / "days" / "2026-11-05.json").write_text("{}")
    original = reader

    def with_new_day(day, r):
        return dict(cells=all_cells(25.0), received_at_utc="2026-11-05T06:00:00+00:00", version="V07C") if day == date(2026, 11, 5) else original(day, r)
    data = observed.summary(root=root, reader=with_new_day)
    assert data["last_day"] == "2026-11-05" and data["daily"][-1]["nairobi_mm"] == 25.0


def test_endpoint_and_download_are_staff_only(api, store, monkeypatch):
    client, _ = api
    root, reader, _, _ = store
    monkeypatch.setattr(imerg_early, "store_path", lambda: root)
    monkeypatch.setattr(imerg_early, "read_day", reader)
    assert client.get("/staff/observed-rainfall").status_code == 401
    assert client.get("/exports/observed-rainfall.csv").status_code == 401
    body = client.get("/staff/observed-rainfall", headers=token()).json()
    assert body["contract_version"] == "observed-rainfall-v1" and len(body["climatology"]) == 12
    text = client.get("/exports/observed-rainfall.csv?start=2026-11-04", headers=token()).content.decode("utf-8")[1:]
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["date_utc_day", "area", "rainfall_mm", "source"]
    assert rows[1][:3] == ["2026-11-04", "Nairobi (all sub-counties)", "0.0"] and len(rows) == 1 + 18
