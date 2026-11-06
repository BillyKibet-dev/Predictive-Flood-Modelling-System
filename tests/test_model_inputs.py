"""Model/weather contract tests; no network or application database writes."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import requests

from src.api.services.ml_service import MLService
from src.api.services.model_contract import (
    FEATURE_COLUMNS, ModelInputError, ModelUnavailableError, validate_artifacts, validate_feature_row,
)
from src.api.services.weather_service import (
    EXPECTED_UNITS, WeatherService, parse_weather_response, scs_wl,
)

NOW = datetime(2026, 10, 25, 9, 30, tzinfo=timezone.utc)  # 12:30 Nairobi


def weather_payload():
    start = datetime(2026, 10, 24)
    times = [(start + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(48)]
    return {"utc_offset_seconds": 10800, "hourly_units": dict(EXPECTED_UNITS), "hourly": {
        "time": times, "temperature_2m": [20.0] * 48, "relative_humidity_2m": [65.0] * 48,
        "wind_speed_10m": [10.0] * 48, "soil_moisture_0_to_7cm": [0.25] * 24 + [0.35] * 24,
        "precipitation": [1.0] * 24 + [2.0] * 13 + [999.0] * 11,
    }}


def feature_row():
    return WeatherService().compute_features(parse_weather_response(weather_payload(), NOW))


def test_nairobi_snapshot_excludes_future_rain_and_keeps_both_days_separate():
    snapshot = parse_weather_response(weather_payload(), NOW)
    assert snapshot["timestamp"] == "2026-10-25T12:00:00+03:00"
    assert snapshot["today_rainfall_total"] == 26
    assert snapshot["yesterday_rainfall_total"] == 24
    assert snapshot["yesterday_soil_moisture"] == 0.25
    row = WeatherService().compute_features(snapshot)
    assert set(row) == set(FEATURE_COLUMNS)
    assert row["delta_water_level"] == pytest.approx(scs_wl(26, sm=0.35) - scs_wl(24, sm=0.25))
    assert row["month"] == 10 and row["is_short_rains"] == 1
    assert row["day_of_year"] == 298


def test_midnight_uses_nairobi_date_even_when_utc_is_previous_day():
    row = WeatherService().compute_features(parse_weather_response(
        weather_payload(), datetime(2026, 10, 24, 21, 10, tzinfo=timezone.utc)))
    assert row["day_of_year"] == 298
    assert row["delta_water_level"] == pytest.approx(scs_wl(2, sm=0.35) - scs_wl(24, sm=0.25))


@pytest.mark.parametrize("change", [
    lambda p: p["hourly"]["precipitation"].__setitem__(0, None),
    lambda p: p["hourly"]["precipitation"].__setitem__(25, float("nan")),
    lambda p: p["hourly"]["precipitation"].__setitem__(24, -1),
    lambda p: p["hourly"]["soil_moisture_0_to_7cm"].__setitem__(0, None),
    lambda p: p["hourly"]["temperature_2m"].pop(),
    lambda p: p["hourly"]["time"].__setitem__(5, p["hourly"]["time"][4]),
    lambda p: p["hourly_units"].__setitem__("wind_speed_10m", "m/s"),
    lambda p: p.__setitem__("utc_offset_seconds", 0),
    lambda p: p.__setitem__("hourly_units", None),
])
def test_missing_history_invalid_numbers_units_and_duplicate_hours_are_rejected(change):
    payload = weather_payload()
    change(payload)
    with pytest.raises((ModelInputError, ValueError)):
        parse_weather_response(payload, NOW)


def test_missing_hour_and_old_response_do_not_fall_back_to_a_previous_day():
    payload = weather_payload()
    payload["hourly"]["time"][36] = "2026-10-25T12:01"
    with pytest.raises(ModelInputError, match="coverage"):
        parse_weather_response(payload, NOW)
    with pytest.raises(ModelInputError, match="coverage"):
        parse_weather_response(weather_payload(), NOW + timedelta(days=2))


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True, "20"])
def test_model_inputs_cannot_be_silently_defaulted_or_non_numeric(value):
    row = feature_row()
    row["temperature_2m"] = value
    with pytest.raises(ModelInputError):
        validate_feature_row(row)


def test_model_feature_order_is_fixed_and_locations_are_not_model_inputs():
    row = feature_row()
    assert validate_feature_row(dict(reversed(list(row.items())))) == [row[name] for name in FEATURE_COLUMNS]
    assert validate_feature_row({**row, "latitude": -1.3, "longitude": 36.8}) == validate_feature_row(row)
    missing = dict(row)
    missing.pop("month")
    with pytest.raises(ModelInputError):
        validate_feature_row(missing)


def test_artifact_order_width_and_class_order_must_agree():
    model = SimpleNamespace(n_features_in_=9, classes_=np.array([0, 1, 2, 3]))
    scaler = SimpleNamespace(n_features_in_=9)
    validate_artifacts(model, scaler, list(FEATURE_COLUMNS))
    for bad_model, bad_scaler, columns in [
        (model, scaler, list(reversed(FEATURE_COLUMNS))),
        (model, SimpleNamespace(n_features_in_=8), FEATURE_COLUMNS),
        (SimpleNamespace(n_features_in_=8, classes_=[0, 1, 2, 3]), scaler, FEATURE_COLUMNS),
        (SimpleNamespace(n_features_in_=9, classes_=[0, 1, 2]), scaler, FEATURE_COLUMNS),
    ]:
        with pytest.raises(ModelInputError):
            validate_artifacts(bad_model, bad_scaler, columns)


def test_missing_model_cannot_return_mock_moderate_predictions():
    service = MLService.__new__(MLService)
    service.model = service.scaler = service.feature_cols = None
    with pytest.raises(ModelUnavailableError):
        service.predict(feature_row())


def test_bad_inputs_are_rejected_before_scaling_or_inference():
    service = MLService.__new__(MLService)
    service.model, service.scaler, service.feature_cols = Mock(), Mock(), list(FEATURE_COLUMNS)
    with pytest.raises(ModelInputError):
        service.predict({})
    service.scaler.transform.assert_not_called()
    service.model.predict.assert_not_called()


def test_weather_fetch_requests_recent_history_and_explicit_units(monkeypatch):
    response = Mock()
    response.json.return_value = weather_payload()
    request = Mock(return_value=response)
    monkeypatch.setattr("src.api.services.weather_service.requests.get", request)
    parser = Mock(return_value={"validated": True})
    monkeypatch.setattr("src.api.services.weather_service.parse_weather_response", parser)
    assert WeatherService().get_current_weather() == {"validated": True}
    params = request.call_args.kwargs["params"]
    assert params["past_days"] == 1 and params["forecast_days"] == 1
    assert params["wind_speed_unit"] == "kmh" and params["timezone"] == "Africa/Nairobi"
    assert request.call_args.kwargs["timeout"] == 15
    request.side_effect = requests.Timeout()
    assert WeatherService().get_current_weather() is None
