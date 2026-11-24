"""Live track record: past forecasts scored against satellite rain, with no look-ahead."""
from datetime import date, datetime, timedelta, timezone

import pytest

from src.api.services import imerg_early, live_verification as lv
from src.api.services import monitoring_point_features as points
from src.api.utils.security import create_access_token
from tests.test_api import api, password_hash  # noqa: F401  (fixtures)


def token(role="officer"):
    return {"Authorization": "Bearer " + create_access_token({"sub": f"{role}@example.test"})}


def test_scores_count_hits_misses_and_false_alarms_and_agreement():
    pairs = [("High", "High"), ("Low", "Extreme"), ("Extreme", "Moderate"), ("Low", "Low"), ("Moderate", "Low")]
    s = lv.scores(pairs)
    assert (s["hits"], s["misses"], s["false_alarms"], s["correct_quiet"]) == (1, 1, 1, 2)
    assert s["pod"] == 0.5 and s["far"] == 0.5 and s["csi"] == 0.333
    assert s["exact"] == 0.4 and s["within_one"] == 0.6
    assert s["wet"]["hits"] == 2 and s["wet"]["misses"] == 1 and s["wet"]["false_alarms"] == 1
    assert sum(map(sum, s["confusion"])) == 5 and s["confusion"][2][2] == 1
    empty = lv.scores([])
    assert empty["n"] == 0 and empty["pod"] is None and empty["exact"] is None


def week(cell, amounts, *, broken=None):
    """Reader returning `amounts` (oldest first) for the 7 days ending 10 Nov at one cell."""
    days = {date(2026, 11, 4) + timedelta(days=i): a for i, a in enumerate(amounts)}

    def reader(day, root):
        if day not in days:
            return None
        ok = day != broken
        return dict(cells={cell: dict(precipitation_mm=days[day] if ok else None, complete=ok)},
                    received_at_utc=f"{day + timedelta(days=1)}T06:00:00+00:00")
    return reader


def test_observed_category_uses_the_label_rule_and_waits_for_all_seven_days():
    cell = "lat884_lon2168"
    assert lv.observed_class(cell, date(2026, 11, 10), week(cell, [0, 0, 0, 0, 0, 0, 22]))["category"] == "High"
    assert lv.observed_class(cell, date(2026, 11, 10), week(cell, [20, 20, 20, 20, 0, 0, 1]))["category"] == "High", "80 mm in 7 days"
    assert lv.observed_class(cell, date(2026, 11, 10), week(cell, [0] * 7, broken=date(2026, 11, 7))) is None
    assert lv.observed_class(cell, date(2026, 11, 11), week(cell, [0] * 7)) is None, "11 Nov itself not stored yet"


def test_satellite_days_received_after_the_forecast_are_hidden():
    lat, lon = -1.2864, 36.8172
    cell = imerg_early.cell_id(*imerg_early.cell_index(lat, lon))
    reader = week(cell, [1] * 7)   # each day is received the next morning
    early = lv._antecedent_as_of(datetime(2026, 11, 8, 12, tzinfo=timezone.utc), reader)
    result = early(lat, lon, date(2026, 11, 10))      # needs 5..9 Nov; 9 Nov arrives 10 Nov
    assert result.status == "UNAVAILABLE" and result.reason == "NOT_YET_RECEIVED_AT_ISSUE"


@pytest.fixture
def two_days(monkeypatch):
    """Forecasts for 9 and 10 Nov at every located place; satellite rain complete for 10 Nov only."""
    rows = [r for r in points.feature_table()["rows"] if r["coordinates"]]
    stored = datetime(2026, 11, 8, 20, tzinfo=timezone.utc)
    receipts = {d: dict(stored_at=stored + timedelta(days=i), reference=dict(sha256=f"{i}" * 64)) for i, d in enumerate(["2026-11-09", "2026-11-10"])}
    monkeypatch.setattr(lv, "_receipts_by_target", lambda store: receipts)
    lv._verified.clear()

    def issued(store, reference, stored_at, reader):
        shown = "High" if reference["sha256"].startswith("1") else "Low"
        return dict(collection=dict(model_version="stage2-xgb-test"), areas=[
            dict(area_id=r["area_id"], status="AVAILABLE", proxy_class=shown, rule_class="Moderate", method="stage2_xgboost_guarded",
                 rainfall_mm=25.0, accumulation_7d_mm=40.0) for r in rows])

    def reader(day, root):   # 30 mm fell on 10 Nov everywhere; nothing collected before 4 Nov
        if not date(2026, 11, 4) <= day <= date(2026, 11, 10):
            return None
        cells = {imerg_early.cell_id(i, j): dict(precipitation_mm=30.0 if day == date(2026, 11, 10) else 0.0, complete=True)
                 for i in range(imerg_early.LAT_INDEX[0], imerg_early.LAT_INDEX[1] + 1)
                 for j in range(imerg_early.LON_INDEX[0], imerg_early.LON_INDEX[1] + 1)}
        return dict(cells=cells, received_at_utc=f"{day}T06:00:00+00:00")
    return rows, issued, reader


def test_evaluation_scores_the_map_and_the_rule_on_the_same_days(two_days):
    rows, issued, reader = two_days
    result = lv.evaluation(today=date(2026, 11, 12), store=object(), reader=reader, issued=issued)
    assert result["contract_version"] == "live-verification-v1"
    assert result["days_verified"] == 1 and result["days_waiting"] == 1, "9 Nov needs 3 Nov, never collected"
    assert result["place_days"] == len(rows) and result["cell_days"] <= len(rows)
    assert result["shown"]["hits"] == len(rows) and result["shown"]["misses"] == 0, "the map said High; 30 mm fell"
    assert result["rule"]["misses"] == len(rows), "the rule said Moderate"
    assert result["amounts"] == dict(mae_mm=5.0, bias_mm=-5.0)
    assert [d["status"] for d in result["daily"]] == ["WAITING_FOR_SATELLITE", "VERIFIED"]


def test_today_and_future_days_are_never_scored(two_days):
    _, issued, reader = two_days
    result = lv.evaluation(today=date(2026, 11, 10), store=object(), reader=reader, issued=issued)
    assert [d["date"] for d in result["daily"]] == ["2026-11-09"]


def test_endpoint_is_staff_only(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(lv, "evaluation", lambda: dict(contract_version="live-verification-v1"))
    assert client.get("/staff/model-verification").status_code == 401
    assert client.get("/staff/model-verification", headers=token()).json()["contract_version"] == "live-verification-v1"
