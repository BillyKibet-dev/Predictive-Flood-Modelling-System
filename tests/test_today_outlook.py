"""Same-day outlook: 3-hour windows, intensity words, and today's class from the Stage 2 model."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.services import today_outlook as t
from src.modeling.stage2.features import FeatureError, build_features

TODAY = date(2026, 11, 16)
MIDNIGHT = datetime(2026, 11, 16)


def test_intensity_words_follow_standard_hourly_rates():
    assert t.intensity([0.0, 0.1, 0.0]) == "none"
    assert t.intensity([0.5, 2.4, 0.3]) == "light"
    assert t.intensity([1.0, 5.0, 0.2]) == "moderate"
    assert t.intensity([0.0, 8.0, 0.0]) == "heavy"


def test_windows_start_at_the_current_hour_and_need_every_hour():
    spans = t.windows(datetime(2026, 11, 16, 14, 25))
    assert [(n, s.hour, e.hour) for n, s, e in spans] == [("next_3h", 14, 17), ("next_3_6h", 17, 20)]
    rain = {MIDNIGHT + timedelta(hours=h): 1.0 for h in range(15, 21)}
    assert t.window_values(rain, *spans[0][1:]) == [1.0, 1.0, 1.0]
    del rain[MIDNIGHT + timedelta(hours=19)]
    assert t.window_values(rain, *spans[1][1:]) is None, "a missing hour is never read as dry"


def test_newer_run_overrides_older_hours_and_nulls_are_dropped():
    old = dict(hourly_rainfall=[dict(interval_end="2026-11-16T08:00:00+00:00", precipitation_mm=4.0),
                                dict(interval_end="2026-11-16T09:00:00+00:00", precipitation_mm=None)])
    new = dict(issue_day_rainfall=[dict(interval_end="2026-11-16T08:00:00+00:00", precipitation_mm=1.0)])
    rain = t.hourly_rain(old)
    rain.update(t.hourly_rain(new))
    assert rain == {datetime(2026, 11, 16, 11): 1.0}   # 08 UTC = 11:00 EAT; the null hour is absent


class FixedModel:
    version = "fixture"

    def __init__(self):
        self.features = None

    def classify(self, features, rule_level):
        self.features = features
        return dict(risk_level=2, guard_applied=False, scores={})


def base_weather(rain_per_hour=1.0):
    hours = [MIDNIGHT + timedelta(hours=h) for h in range(1, 25)]
    utc = lambda local: (local - timedelta(hours=3)).isoformat() + "+00:00"
    return dict(hourly_rainfall=[dict(interval_end=utc(h), precipitation_mm=rain_per_hour) for h in hours],
                hourly_weather=[dict(valid_at=utc(MIDNIGHT + timedelta(hours=h)), temperature_2m=20.0, relative_humidity_2m=80.0,
                                     wind_speed_10m=10.0, soil_moisture_0_to_7cm=0.3) for h in range(24)],
                issue_day_rainfall=[])


def test_today_runs_through_the_model_with_today_as_the_target_day():
    model, weather = FixedModel(), base_weather(1.0)
    rain = t.hourly_rain(weather)
    category, rule_category, method, status, guard, complete = t.classify_today(
        today_rain=rain, base_weather=weather, observed_days=[1, 2, 3, 4, 5], issue_day_total=6.0, today=TODAY, model=model)
    assert (category, method, status, complete) == ("High", "stage2_xgboost_guarded", "APPLIED", True)
    f = model.features
    assert f["tomorrow_rain_mm"] == 24.0 and f["today_forecast_rain_mm"] == 6.0 and f["accumulation_7d_mm"] == 45.0
    assert rule_category == "High"      # 24 mm in the day reaches the 20 mm High threshold


def test_missing_inputs_fall_back_to_the_rule_as_a_lower_bound():
    weather = base_weather(1.0)
    rain = t.hourly_rain(weather)
    rain.pop(MIDNIGHT + timedelta(hours=5))
    out = t.classify_today(today_rain=rain, base_weather=weather, observed_days=[1, 2, 3, 4, 5], issue_day_total=6.0,
                           today=TODAY, model=FixedModel())
    assert out[2:4] == ("rule_lower_bound", "INPUTS_INCOMPLETE") and out[0] == "High"   # 23 mm still >= 20
    out = t.classify_today(today_rain=t.hourly_rain(weather), base_weather=weather, observed_days=None, issue_day_total=6.0,
                           today=TODAY, model=FixedModel())
    assert out[3] == "INPUTS_INCOMPLETE"


def test_training_features_are_unchanged_when_no_issue_day_total_is_given():
    hourly = {"time": [], "precipitation": [], "temperature_2m": [], "relative_humidity_2m": [], "wind_speed_10m": [], "soil_moisture_0_to_7cm": []}
    with pytest.raises(FeatureError):
        build_features(hourly, date(2026, 11, 15), [0] * 5)          # issue-day hours still required
    with pytest.raises(FeatureError):
        build_features(hourly, date(2026, 11, 15), [0] * 5, issue_day_total=-1)


def test_endpoint_is_public_and_never_cached(monkeypatch):
    monkeypatch.setattr(t, "get_today", lambda: dict(contract_version=t.CONTRACT, areas=[]))
    with TestClient(app) as client:
        response = client.get("/monitoring-areas/today")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
