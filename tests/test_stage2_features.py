"""Stage 2 features use exactly the live Stage 1 windows and never fill gaps."""
from datetime import date

import pytest

from src.api.services import monitoring_point_features as points
from src.api.services import rainfall_risk_rule as rule
from src.api.services.forecast_proxy_context import attach_forecast_proxy
from src.api.services.imerg_early import Antecedent
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.modeling.stage2.features import FEATURE_COLUMNS, FeatureError, build_features
from tests.test_monitoring_point_features import NOW, payload, save

ISSUE = date(2026, 11, 12)          # fixture run 00 UTC on 12 Nov; precipitation value = hour index
OBSERVED = [1.0, 2.0, 3.0, 4.0, 5.0]


def test_windows_match_the_live_rule_exactly(tmp_path):
    hourly = payload()[0]["hourly"]
    features = build_features(hourly, ISSUE, OBSERVED)
    assert list(features) == list(FEATURE_COLUMNS)
    assert features["tomorrow_rain_mm"] == sum(range(22, 46))
    assert features["today_forecast_rain_mm"] == sum(range(1, 22))
    assert features["observed_3d_mm"] == 12 and features["observed_yesterday_mm"] == 5
    store = LocalEvidenceStore(tmp_path)
    table = attach_forecast_proxy(points.join_weather(store, save(store), now=NOW), now=NOW)
    live = rule.attach_rainfall_risk(table, antecedent=lambda lat, lon, d: Antecedent("AVAILABLE", sum(OBSERVED), "c", []))
    risk = next(r for r in live["rows"] if r["weather"])["rainfall_risk_context"]
    assert risk["accumulation_7d_mm"] == pytest.approx(features["accumulation_7d_mm"])
    assert rule.CLASSES.index(risk["risk_class"]) == features["rule_class_level"]


def test_burst_and_rainy_hour_features():
    hourly = payload()[0]["hourly"]
    features = build_features(hourly, ISSUE, OBSERVED)
    assert features["tomorrow_max_1h_mm"] == 45 and features["tomorrow_max_3h_mm"] == 43 + 44 + 45
    assert features["tomorrow_rainy_hours"] == 24


@pytest.mark.parametrize("observed", [[1, 2, 3, 4], [1, 2, None, 4, 5], [1, 2, -1, 4, 5]])
def test_incomplete_observations_are_rejected(observed):
    with pytest.raises(FeatureError):
        build_features(payload()[0]["hourly"], ISSUE, observed)


def test_missing_forecast_hour_is_rejected_not_zero():
    hourly = payload()[0]["hourly"]
    hourly["precipitation"][30] = None
    with pytest.raises(FeatureError):
        build_features(hourly, ISSUE, OBSERVED)
