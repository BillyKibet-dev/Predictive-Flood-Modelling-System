"""Stage 1 rule: IMERG Early antecedent store, observed+forecast v1-rule scoring, outlook v2.

No network: NASA responses are synthetic text in the real Earthdata Cloud DAP4 CSV layout
(and the legacy DAP2 ASCII layout, still accepted for previously stored days).
"""
from copy import deepcopy
from datetime import date, timedelta
import json

import pytest

from src.api.services import imerg_early as im
from src.api.services import monitoring_point_features as features
from src.api.services import point_outlook
from src.api.services import rainfall_risk_rule as rule
from src.api.services.forecast_proxy_context import attach_forecast_proxy
from src.api.services.operational_source_storage import LocalEvidenceStore
from tests.test_monitoring_point_features import NOW, payload, save

LATS = range(im.LAT_INDEX[0], im.LAT_INDEX[1] + 1)
LONS = range(im.LON_INDEX[0], im.LON_INDEX[1] + 1)
NL = chr(10)


def _value(i, j, var, amount, count, override):
    a, c = (override or {}).get(im.cell_id(i, j), (amount, count))
    return str(a if var == "precipitation" else c)


def csv_body(amount=2.5, count=48, override=None):
    """Synthetic Earthdata Cloud OPeNDAP DAP4 CSV subset; ``override`` maps cell_id -> (amount, count)."""
    lines = ["Dataset: 3B-DAY-E.MS.MRG.3IMERG.20261113-S000000-E235959.V07C.nc4",
             "/lon, " + ", ".join(str(im.cell_centre(LATS[0], j)[1]) for j in LONS),
             "/lat, " + ", ".join(str(im.cell_centre(i, LONS[0])[0]) for i in LATS)]
    for var in ("precipitation", "precipitation_cnt"):
        for k, j in enumerate(LONS):
            lines.append(f"/{var}[0][{k}], " + ", ".join(_value(i, j, var, amount, count, override) for i in LATS))
    return NL.join(lines) + NL


def ascii_body(amount=2.5, count=48, override=None):
    """Legacy GES DISC DAP2 ASCII subset (format of days stored before the cloud switch)."""
    lines = ["Dataset: 3B-DAY-E.MS.MRG.3IMERG.20261113-S000000-E235959.V07C.nc4"]
    for var in ("precipitation", "precipitation_cnt"):
        lines.append(f"{var}.lat, " + ", ".join(str(im.cell_centre(i, LONS[0])[0]) for i in LATS))
        for j in LONS:
            lines.append(f"{var}.{var}[{var}.time=20000][{var}.lon={im.cell_centre(LATS[0], j)[1]}], "
                         + ", ".join(_value(i, j, var, amount, count, override) for i in LATS))
    return NL.join(lines) + NL


class FakeResponse:
    def __init__(self, status, text):
        self.status_code, self.text, self.content = status, text, text.encode()


class FakeSession:
    """Cloud OPeNDAP stand-in; ``catalog`` is the matching CMR stand-in."""
    def __init__(self, days, body=None, versions=None):
        self.days, self.body, self.versions = set(days), body or (lambda d: csv_body()), versions or {}
        self.calls, self.catalog_calls = [], []

    def catalog(self, year, month):
        self.catalog_calls.append((year, month))
        out = {}
        for d in self.days:
            if (d.year, d.month) == (year, month):
                v = self.versions.get(d, "V07C")
                out[d] = (v, f"3B-DAY-E.MS.MRG.3IMERG.{d:%Y%m%d}-S000000-E235959.{v}.nc4")
        return out

    def get(self, url, timeout=None):
        self.calls.append(url)
        assert url.startswith(im.CLOUD_OPENDAP) and ".dap.csv?dap4.ce=" in url
        stamp = url.split("3IMERG.")[1][:8]
        return FakeResponse(200, self.body(date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))))


def collect(days, root, session):
    return im.collect_days(days, root=root, session=session, catalog=session.catalog, pause=0)


ISSUE = date(2026, 11, 12)   # matches the point-feature fixture: target 13 Nov
DAYS = im.antecedent_days(ISSUE)


# ------------------------------------------------------------- IMERG store
def test_every_located_pin_falls_inside_the_collected_box():
    for row in features.feature_table()["rows"]:
        if row["coordinates"]:
            lon, lat = row["coordinates"]
            assert im.cell_id(*im.cell_index(lat, lon)).startswith("lat")
    with pytest.raises(ValueError):
        im.cell_index(0.0, 36.8)


def test_antecedent_window_is_five_complete_utc_days_before_issue():
    assert DAYS == [date(2026, 11, 7), date(2026, 11, 8), date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11)]


def test_both_response_formats_parse_to_the_same_cells():
    assert im.parse_dap4_csv(csv_body(amount=3.0)) == im.parse_ascii(ascii_body(amount=3.0))


def test_collect_parses_stores_once_and_sums_the_pin_cell(tmp_path):
    session = FakeSession(DAYS, body=lambda d: csv_body(amount=d.day))   # 7+8+9+10+11
    summary = collect(DAYS, tmp_path, session)
    assert summary["stored"] == [d.isoformat() for d in DAYS] and not summary["failed"]
    assert session.catalog_calls == [(2026, 11)]                          # one catalogue query for the month
    a = im.antecedent(-1.286, 36.817, ISSUE, root=tmp_path)
    assert a.status == "AVAILABLE" and a.total_mm == 45 and a.cell == "lat887_lon2168"
    assert {d["version"] for d in a.days} == {"V07C"}
    assert im.read_day(DAYS[0], tmp_path)["access"] == "earthdata-cloud-opendap"
    again = collect(DAYS, tmp_path, session)
    assert again["already_stored"] == [d.isoformat() for d in DAYS] and len(session.calls) == 5


def test_unpublished_and_incomplete_days_are_missing_not_zero(tmp_path):
    partial = {"lat887_lon2168": (3.0, 47)}
    session = FakeSession(DAYS[:-1], body=lambda d: csv_body(override=partial if d == DAYS[0] else None))
    summary = collect(DAYS, tmp_path, session)
    assert summary["not_yet_published"] == [DAYS[-1].isoformat()]
    a = im.antecedent(-1.286, 36.817, ISSUE, root=tmp_path)
    assert a.status == "UNAVAILABLE" and a.total_mm is None
    assert DAYS[0].isoformat() in a.reason and DAYS[-1].isoformat() in a.reason
    fill = FakeSession([DAYS[-1]], body=lambda d: csv_body(override={"lat887_lon2168": (im.FILL_VALUE, 48)}))
    collect([DAYS[-1]], tmp_path, fill)
    assert im.read_day(DAYS[-1], tmp_path)["cells"]["lat887_lon2168"]["precipitation_mm"] is None


def test_tampered_store_and_unexpected_grid_are_rejected(tmp_path):
    collect(DAYS, tmp_path, FakeSession(DAYS))
    record = im.record_path(tmp_path, DAYS[0])
    doc = json.loads(record.read_bytes()); doc["cells"]["lat887_lon2168"]["precipitation_mm"] = 99.0
    record.write_text(json.dumps(doc))
    with pytest.raises(im.ImergError):
        im.read_day(DAYS[0], tmp_path)
    assert im.antecedent(-1.286, 36.817, ISSUE, root=tmp_path).status == "UNAVAILABLE"
    with pytest.raises(im.ImergError):
        im.parse_dap4_csv(csv_body().replace("/lat, -1.55", "/lat, -1.65"))
    with pytest.raises(im.ImergError):
        im.parse_ascii(ascii_body().replace("precipitation.lat, -1.55", "precipitation.lat, -1.65"))


def test_newest_minor_version_is_used_and_recorded(tmp_path):
    session = FakeSession([DAYS[0]])
    names = {v: f"3B-DAY-E.MS.MRG.3IMERG.20261107-S000000-E235959.{v}.nc4" for v in ("V07B", "V07C")}

    def both(year, month):
        return {DAYS[0]: max((v, n) for v, n in names.items())}
    im.collect_days([DAYS[0]], root=tmp_path, session=session, catalog=both, pause=0)
    assert im.read_day(DAYS[0], tmp_path)["version"] == "V07C" and "V07C" in session.calls[0]


def test_cmr_catalogue_parses_titles_and_picks_the_newest_version():
    titles = [f"GPM_3IMERGDE.07:3B-DAY-E.MS.MRG.3IMERG.202402{d:02d}-S000000-E235959.V07B.nc4" for d in (1, 2)]
    titles.append("GPM_3IMERGDE.07:3B-DAY-E.MS.MRG.3IMERG.20240202-S000000-E235959.V07C.nc4")

    class Response:
        status_code = 200

        def json(self):
            return {"feed": {"entry": [{"title": t} for t in titles]}}

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            assert url == im.CMR_GRANULES and params["short_name"] == "GPM_3IMERGDE"
            assert "Authorization" not in (headers or {})
            assert params["temporal"] == "2024-02-01T00:00:00Z,2024-02-29T23:59:59Z"
            return Response()

    found = im.cmr_month(2024, 2, http=Http())
    assert found[date(2024, 2, 1)][0] == "V07B" and found[date(2024, 2, 2)][0] == "V07C"


def test_safe_hook_is_disabled_in_tests_and_never_raises():
    assert im.collect_for_issue_safely(ISSUE) == {"status": "DISABLED"}


# --------------------------------------------------------------- the rule
@pytest.mark.parametrize("daily,accum,expected,driver", [
    (0, 0, "Low", "tomorrow"), (4.99, 24.99, "Low", "tomorrow"), (5, 0, "Moderate", "tomorrow"),
    (0, 25, "Moderate", "accumulation"), (19.9, 80, "High", "accumulation"), (20, 79.9, "High", "tomorrow"),
    (0, 150, "Extreme", "accumulation"), (40, 0, "Extreme", "tomorrow"), (3, None, "Low", "tomorrow_only"),
    (45, None, "Extreme", "tomorrow_only")])
def test_v1_label_rule_boundaries(daily, accum, expected, driver):
    assert rule.rule_class(daily, accum) == (expected, driver)


@pytest.mark.parametrize("bad", [-1, float("nan"), None, "5"])
def test_invalid_rain_never_scores(bad):
    with pytest.raises(ValueError):
        rule.rule_class(bad, 10)


def small_payload(value=0.1):
    items = payload()
    for item in items:
        item["hourly"]["precipitation"] = [value] * 72
    return items


def verified_table(tmp_path, items, received=NOW):
    store = LocalEvidenceStore(tmp_path / "points")
    ref = save(store, items, received=received)
    return attach_forecast_proxy(features.join_weather(store, ref, now=received), now=received)


def fixed_antecedent(total):
    def lookup(lat, lon, issue_date):
        assert issue_date == ISSUE
        return im.Antecedent("AVAILABLE", total, "lat887_lon2168", [])
    return lookup


def test_issue_day_remainder_covers_the_21_hours_after_00_utc(tmp_path):
    table = verified_table(tmp_path, payload())
    row = next(r for r in table["rows"] if r["weather"])
    rain = row["weather"]["issue_day_rainfall"]
    assert len(rain) == 21 and rain[0]["interval_start"].startswith("2026-11-12T00:00")
    assert rain[-1]["interval_end"].startswith("2026-11-12T21:00")
    assert [r["precipitation_mm"] for r in rain] == list(range(1, 22))     # fixture rain = hour index
    assert rule.issue_day_forecast_mm(row["weather"]) == sum(range(1, 22))


def test_accumulation_upgrades_a_low_tomorrow(tmp_path):
    table = rule.attach_rainfall_risk(verified_table(tmp_path, small_payload(0.1)), antecedent=fixed_antecedent(30.0))
    risk = next(r for r in table["rows"] if r["weather"])["rainfall_risk_context"]
    assert risk["method"] == "observed_plus_forecast_rule" and risk["accumulation_complete"] is True
    assert risk["tomorrow_forecast_mm"] == pytest.approx(2.4) and risk["issue_day_forecast_mm"] == pytest.approx(2.1)
    assert risk["accumulation_7d_mm"] == pytest.approx(34.5)
    assert (risk["risk_class"], risk["class_driver"]) == ("Moderate", "accumulation")
    assert risk["flood_probability"] is None and risk["model_version"] is None


def test_missing_observed_rain_scores_a_flagged_lower_bound_and_says_why(tmp_path):
    table = rule.attach_rainfall_risk(verified_table(tmp_path, small_payload(0.1)))   # empty isolated store
    risk = next(r for r in table["rows"] if r["weather"])["rainfall_risk_context"]
    assert risk["method"] == "observed_plus_forecast_rule_lower_bound" and risk["accumulation_complete"] is False
    assert risk["antecedent_observed_mm"] is None                     # missing, not an observed zero
    assert risk["accumulation_7d_mm"] == pytest.approx(2.1 + 2.4) and risk["risk_class"] == "Low"
    assert risk["fallback_reasons"][0].startswith("IMERG_DAYS_MISSING")


def test_lower_bound_still_raises_class_when_forecast_alone_crosses_a_threshold(tmp_path):
    table = rule.attach_rainfall_risk(verified_table(tmp_path, small_payload(1.0)))   # no observed days
    risk = next(r for r in table["rows"] if r["weather"])["rainfall_risk_context"]
    # tomorrow 24 mm (High) ; at least 21 + 24 = 45 mm over 7 days (Moderate) -> High from tomorrow
    assert (risk["risk_class"], risk["class_driver"]) == ("High", "tomorrow")


def test_missing_forecast_hours_before_the_run_start_keep_observed_rain(tmp_path):
    items = small_payload(0.1)
    for item in items:
        item["hourly"]["precipitation"][5] = None          # 08:00 EAT on the issue day
    table = rule.attach_rainfall_risk(verified_table(tmp_path, items), antecedent=fixed_antecedent(200.0))
    risk = next(r for r in table["rows"] if r["weather"])["rainfall_risk_context"]
    assert risk["missing_issue_day_hours"] == 1 and "ISSUE_DAY_FORECAST_HOURS_MISSING:1" in risk["fallback_reasons"]
    assert risk["accumulation_complete"] is False and risk["accumulation_7d_mm"] == pytest.approx(200 + 2.0 + 2.4)
    assert (risk["risk_class"], risk["class_driver"]) == ("Extreme", "accumulation")   # lower bound already >= 150


def test_stale_forecast_stays_unavailable_even_with_observed_rain(tmp_path):
    late = NOW + timedelta(hours=7)
    table = verified_table(tmp_path, payload(), received=NOW)
    attach_forecast_proxy(table, now=late)
    rule.attach_rainfall_risk(table, antecedent=fixed_antecedent(500.0))
    assert all(r["rainfall_risk_context"]["risk_class"] is None for r in table["rows"])


def test_outlook_contract_exposes_the_rule_components_when_the_model_is_off(tmp_path):
    doc = point_outlook.summarize(verified_table(tmp_path, small_payload(0.1)), NOW, antecedent=fixed_antecedent(90.0))
    assert doc["contract_version"] == "monitoring-rainfall-outlook-v3"
    assert doc["collection"]["method"] == "stage2_xgboost_with_rule_fallback" and doc["collection"]["model_version"] is None
    assert doc["collection"]["thresholds"] == dict(tomorrow_mm=[5.0, 20.0, 40.0], accumulation_mm=[25.0, 80.0, 150.0],
                                                   accumulation_window_hours=165)
    area = next(a for a in doc["areas"] if a["status"] == "AVAILABLE")
    assert area["proxy_class"] == "High" and area["class_driver"] == "accumulation"
    assert area["accumulation_7d_mm"] == pytest.approx(90 + 2.1 + 2.4)
    assert area["rainfall_mm"] == pytest.approx(2.4) and area["antecedent_cell"] == "lat887_lon2168"
    assert area["rule_class"] == "High" and area["model_status"] == "MODEL_UNAVAILABLE" and area["model_version"] is None
    assert not any(a["reason"] == "LOCATION_UNRESOLVED" for a in doc["areas"])  # All 36 records are located.
