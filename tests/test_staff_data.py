"""Model card, rainfall history and CSV downloads: staff only, spreadsheet-safe, no IP hashes."""
import csv
import io

import pytest

from src.api.services import staff_data
from src.api.utils.security import create_access_token
from tests.test_api import api, password_hash  # noqa: F401  (fixtures)

KIBRA_PIN = dict(latitude=-1.315111, longitude=36.782472)


def token(role="officer"):
    return {"Authorization": "Bearer " + create_access_token({"sub": f"{role}@example.test"})}


def rows(response):
    text = response.content.decode("utf-8")
    assert text.startswith("﻿"), "byte-order mark so Excel reads UTF-8"
    return list(csv.reader(io.StringIO(text[1:])))


@pytest.mark.parametrize("path", ["/staff/model-card", "/staff/rainfall-history", "/exports/citizen-reports.csv",
                                  "/exports/rainfall-outlook.csv", "/exports/rainfall-history.csv"])
def test_everything_here_needs_a_staff_sign_in(api, path):
    client, _ = api
    assert client.get(path).status_code == 401


def test_report_download_is_filtered_spreadsheet_safe_and_never_includes_the_ip_hash(api):
    client, _ = api
    saved = client.post("/citizen-report", json=dict(observed_condition="Street flooding", perceived_severity="Serious",
                        location_description="=HYPERLINK(\"http://example.test\")", description="+254 call me",
                        **KIBRA_PIN)).json()
    response = client.get("/exports/citizen-reports.csv", headers=token())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].startswith('attachment; filename="nairobifloodwatch-community-reports-')
    assert response.headers["cache-control"] == "no-store"
    header, *body = rows(response)
    assert "ip_hash" not in ",".join(header) and len(body) == 1
    record = dict(zip(header, body[0]))
    assert record["report_id"] == str(saved["id"]) and record["sub_county"] == "Kibra"
    assert record["landmark"].startswith("'=") and record["description"].startswith("'+")  # never a formula
    assert record["reported_at_eat"].endswith("+03:00")
    assert len(rows(client.get("/exports/citizen-reports.csv?review_status=Resolved", headers=token()))) == 1
    assert len(rows(client.get("/exports/citizen-reports.csv?end=2020-01-01", headers=token()))) == 1
    assert client.get("/exports/citizen-reports.csv?start=2026-02-01&end=2026-01-01", headers=token()).status_code == 422
    assert client.get("/exports/citizen-reports.csv?review_status=Deleted", headers=token()).status_code == 422


def test_rainfall_history_download_covers_the_requested_days_for_all_eight_zones(api):
    client, _ = api
    response = client.get("/exports/rainfall-history.csv?start=2024-05-01&end=2024-05-02", headers=token("admin"))
    header, *body = rows(response)
    assert header == ["date", "zone_id", "zone", "rainfall_mm", "source"]
    assert len(body) == 16 and {r[0] for r in body} == {"2024-05-01", "2024-05-02"}
    assert client.get("/exports/rainfall-history.csv?start=2010-01-01&end=2026-01-01", headers=token()).status_code == 422


def test_rainfall_history_summary_is_nairobi_wide_and_complete():
    history = staff_data.rainfall_history()
    assert history["first_day"] == "2016-01-01" and history["last_day"] == "2026-09-30"
    assert len(history["monthly"]) == 129 and len(history["monthly_average"]) == 12
    april = history["monthly_average"][3]
    assert april["month"] == 4 and april["average_mm"] == max(m["average_mm"] for m in history["monthly_average"])
    assert history["wettest_days"][0]["mean_mm"] >= history["wettest_days"][-1]["mean_mm"]
    assert [y["complete"] for y in history["yearly"]][-1] is False   # 2026 ends in September


def test_model_card_reports_validation_against_the_rule_and_says_scores_are_not_probabilities():
    card = staff_data.model_card(dict(located=36, available=36, by_status=dict(APPLIED=36)))
    assert card["adoption"]["adopted"] is True
    assert card["validation"]["model"]["high_or_above"]["csi"] > card["validation"]["rule"]["high_or_above"]["csi"]
    assert card["calibration"]["calibrated"] is False
    assert card["live"]["version"] == card["live"]["model_sha256"][:12]
    assert len(card["validation"]["seasons"]) == 9


def test_changed_history_file_is_refused(monkeypatch, tmp_path):
    changed = tmp_path / "chirps.csv"
    changed.write_text("date,zone_id,precipitation\n2016-01-01,cbd,1.0\n", encoding="utf-8")
    monkeypatch.setattr(staff_data, "CHIRPS_PATH", changed)
    staff_data._chirps.cache_clear()
    try:
        with pytest.raises(staff_data.StaffDataUnavailable):
            staff_data.rainfall_history()
    finally:
        monkeypatch.undo()
        staff_data._chirps.cache_clear()


@pytest.mark.parametrize("value,expected", [("=1+1", "'=1+1"), ("-cmd", "'-cmd"), ("@SUM", "'@SUM"),
                                            ("Kibra", "Kibra"), (-1.31, -1.31), (None, ""), (True, "yes")])
def test_safe_cell(value, expected):
    assert staff_data.safe_cell(value) == expected


def test_outlook_download_carries_local_susceptibility(api, monkeypatch):
    from src.api.services import point_outlook
    client, _ = api
    monkeypatch.setattr(point_outlook, "get_outlook", lambda: dict(areas=[dict(
        area_id="NFW-S013", status="AVAILABLE", proxy_class="High", method="stage2_xgboost_guarded", rule_class="Moderate",
        rainfall_mm=22.0, accumulation_7d_mm=60.0, target_start=None, received_at=None, run_at=None, model_version="x")]))
    header, row = rows(client.get("/exports/rainfall-outlook.csv", headers=token()))
    record = dict(zip(header, row))
    assert record["local_susceptibility"] == "Higher" and record["nearest_river"] == "Ngong River"
