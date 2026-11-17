"""Stage 2 live model: package checks, the Extreme guard, live/training feature parity, fallback."""
import json
import shutil
from datetime import date

import pytest

from src.api.services import point_outlook
from src.api.services import rainfall_risk_model as service
from src.api.services import rainfall_risk_rule as rule
from src.api.services.imerg_early import Antecedent
from src.modeling.stage2.features import build_features
from src.modeling.stage2.runtime import DEFAULT_DIR, Stage2Model, Stage2ModelError, guard
from tests.test_monitoring_point_features import NOW, payload
from tests.test_rainfall_risk_rule import small_payload, verified_table

ISSUE = date(2026, 11, 12)
needs_package = pytest.mark.skipif(not (DEFAULT_DIR / "model.json").exists(), reason="trained Stage 2 package not present")


def observed(values):
    def lookup(lat, lon, issue_date):
        days = [dict(utc_day=f"2026-11-{7 + i:02d}", precipitation_mm=v, version="V07C") for i, v in enumerate(values)]
        return Antecedent("AVAILABLE", sum(values), "lat887_lon2168", days)
    return lookup


@pytest.mark.parametrize("model_class,rule_level,expected", [
    (3, 0, (2, True)), (3, 1, (2, True)), (3, 2, (3, False)), (3, 3, (3, False)),
    (2, 0, (2, False)), (1, 3, (1, False)), (0, 0, (0, False))])
def test_extreme_needs_the_rule_to_reach_high(model_class, rule_level, expected):
    assert guard(model_class, rule_level) == expected


@needs_package
def test_package_loads_and_rejects_tampering(tmp_path):
    assert Stage2Model().version.startswith("stage2-xgb-")
    for damage in ("bytes", "version", "adopted", "features"):
        copy = tmp_path / damage
        shutil.copytree(DEFAULT_DIR, copy)
        manifest = json.loads((copy / "manifest.json").read_text())
        if damage == "bytes":
            (copy / "model.json").write_bytes((copy / "model.json").read_bytes() + b" ")
        elif damage == "version":
            manifest["xgboost_version"] = "3.1.3"
        elif damage == "adopted":
            manifest["decision"]["adopted"] = False
        else:
            manifest["feature_columns"] = manifest["feature_columns"][::-1]
        (copy / "manifest.json").write_text(json.dumps(manifest))
        with pytest.raises(Stage2ModelError):
            Stage2Model(copy)


@needs_package
def test_live_features_rebuilt_from_the_receipt_equal_training_features(tmp_path):
    table = rule.attach_rainfall_risk(verified_table(tmp_path, payload()), antecedent=observed([1, 2, 3, 4, 5]))
    row = next(r for r in table["rows"] if r["weather"])
    raw_hourly = payload()[0]["hourly"]                 # what training reads from the archived run
    assert build_features(service.hourly_from_weather(row["weather"]), ISSUE, [1, 2, 3, 4, 5]) == \
        build_features(raw_hourly, ISSUE, [1, 2, 3, 4, 5])


@needs_package
def test_model_applies_where_inputs_are_complete_and_keeps_the_rule_alongside(tmp_path):
    doc = point_outlook.summarize(verified_table(tmp_path, small_payload(0.4)), NOW,
                                  antecedent=observed([2, 3, 10, 4, 1]), model=Stage2Model())
    assert doc["contract_version"] == "monitoring-rainfall-outlook-v3"
    assert doc["collection"]["model_version"].startswith("stage2-xgb-")
    areas = [a for a in doc["areas"] if a["status"] == "AVAILABLE"]
    assert areas and all(a["method"] == "stage2_xgboost_guarded" and a["model_status"] == "APPLIED" for a in areas)
    for a in areas:
        assert abs(sum(a["model_scores"].values()) - 1) < 1e-4
        assert a["rule_class"] == rule.rule_class(a["rainfall_mm"], a["accumulation_7d_mm"])[0]
        if rule.CLASSES.index(a["rule_class"]) < 2:
            assert a["proxy_class"] != "Extreme"
    assert doc["collection"]["flood_probability"] is None


@needs_package
def test_incomplete_inputs_keep_the_stage1_rule(tmp_path):
    doc = point_outlook.summarize(verified_table(tmp_path, small_payload(0.4)), NOW, model=Stage2Model())  # no IMERG days
    area = next(a for a in doc["areas"] if a["status"] == "AVAILABLE")
    assert area["method"] == "observed_plus_forecast_rule_lower_bound" and area["model_status"] == "INPUTS_INCOMPLETE"
    assert area["proxy_class"] == area["rule_class"] and area["model_scores"] is None


def test_missing_package_fails_closed_to_the_rule(tmp_path, monkeypatch):
    from src.api.config import settings
    monkeypatch.setattr(settings, "STAGE2_MODEL_ENABLED", True)
    monkeypatch.setattr(settings, "STAGE2_MODEL_DIR", str(tmp_path / "missing"))
    service._cache.clear()
    doc = point_outlook.summarize(verified_table(tmp_path, small_payload(0.4)), NOW, antecedent=observed([1, 1, 1, 1, 1]))
    area = next(a for a in doc["areas"] if a["status"] == "AVAILABLE")
    assert doc["collection"]["model_version"] is None and area["model_status"] == "MODEL_UNAVAILABLE"
    assert area["method"] == "observed_plus_forecast_rule" and area["proxy_class"] == area["rule_class"]
    service._cache.clear()
