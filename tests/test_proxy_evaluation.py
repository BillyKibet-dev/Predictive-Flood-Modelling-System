"""Daily proxy replay tests using synthetic local data; no network or database."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest
import joblib

from src.api.services.model_contract import FEATURE_COLUMNS, scs_wl
from src.modeling.proxy_evaluation import (
    assign_proxy_labels, chronological_splits, inspect_source, notebook_comparison,
    prediction_metrics, prepare_dataset,
)
from src.modeling import proxy_evaluation
from src.scripts import evaluate_proxy_model


@pytest.fixture
def source_files(tmp_path):
    dates = pd.date_range("2022-12-28", periods=8, freq="D")
    rain = pd.DataFrame({"system:index": dates.strftime("%Y%m%d"),
                         "date": dates.strftime("%Y-%m-%d"), "precipitation": [0, 6, 25, 45, 0, 3, 0, 1]})
    hours = pd.date_range(dates[0], periods=9 * 24, freq="h")
    weather = pd.DataFrame({"time": hours.strftime("%Y-%m-%dT%H:%M"),
                            "temperature_2m": 20 + np.arange(len(hours)) % 24,
                            "relative_humidity_2m": 65, "precipitation": 0.5,
                            "wind_speed_10m": 10, "soil_moisture_0_to_7cm": 0.3})
    rain_path, weather_path = tmp_path / "chirps.csv", tmp_path / "weather.csv"
    rain.to_csv(rain_path, index=False)
    weather.to_csv(weather_path, index=False)
    return rain_path, weather_path


def test_profiles_and_daily_recipe_preserve_files_and_use_daily_means(source_files):
    rain_path, weather_path = source_files
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files]
    frame, profile = prepare_dataset(rain_path, weather_path)
    assert len(frame) == profile["merged_rows"] == 8
    assert profile["excluded_weather_days"] == ["2023-01-05"]
    assert profile["imputation_performed"] is False
    assert profile["accumulation_windows_reconciled"] is False
    assert frame.iloc[0].temperature_2m == 31.5
    assert frame.iloc[0].open_meteo_rainfall_mm == 12
    assert frame.iloc[0].delta_water_level == 0
    assert frame.iloc[2].delta_water_level == pytest.approx(scs_wl(25, sm=0.3) - scs_wl(6, sm=0.3))
    assert frame.iloc[3].rainfall_7day == 76
    assert set(FEATURE_COLUMNS).issubset(frame.columns)
    assert before == [hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files]
    json.dumps(profile, allow_nan=False)


@pytest.mark.parametrize("kind,change", [
    ("chirps", lambda f: f.drop(index=2)),
    ("chirps", lambda f: pd.concat([f.iloc[:1], f], ignore_index=True)),
    ("chirps", lambda f: f.assign(precipitation=[None] + f.precipitation.tolist()[1:])),
    ("chirps", lambda f: f.assign(date="2020-01-01")),
    ("chirps", lambda f: f.assign(precipitation=-1)),
    ("weather", lambda f: f.drop(index=2)),
    ("weather", lambda f: f.iloc[1:]),  # Partial first day cannot masquerade as complete coverage.
    ("weather", lambda f: f.assign(soil_moisture_0_to_7cm=2)),
    ("weather", lambda f: f.assign(wind_speed_10m=float("inf"))),
])
def test_bad_source_values_and_time_axes_are_rejected_without_imputation(source_files, kind, change):
    path = source_files[0 if kind == "chirps" else 1]
    frame = change(pd.read_csv(path))
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        inspect_source(path, kind)


def test_proxy_threshold_boundaries_priority_and_soil_rule():
    labels = assign_proxy_labels([0, 5, 20, 40, 0, 0, 0, 0, 0],
                                 [0, 5, 20, 40, 25, 80, 150, 0, 0],
                                 [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.70, 0.701])
    assert labels.tolist() == [0, 1, 2, 3, 1, 2, 3, 0, 1]


def test_time_splits_use_training_cutoffs_without_random_or_future_rows():
    frame = pd.DataFrame({"date": pd.to_datetime(["2022-12-31", "2023-01-01", "2023-12-31", "2024-01-01"]),
                          "risk_class": [0, 1, 2, 3]})
    splits = chronological_splits(frame)
    assert splits["train"].risk_class.tolist() == [0]
    assert splits["validation"].risk_class.tolist() == [1, 2]
    assert splits["test"].risk_class.tolist() == [3]
    with pytest.raises(ValueError):
        chronological_splits(frame.iloc[:3])


def test_metrics_expose_missed_classes_and_preserve_fixed_confusion_matrix_order():
    result = prediction_metrics([0, 1, 2, 3], [0, 0, 0, 0])
    assert result["accuracy"] == result["weighted_recall"] == 0.25
    assert result["per_class"]["High"]["recall"] == 0
    assert result["confusion_matrix"] == [[1, 0, 0, 0]] * 4
    assert result["auc_roc_weighted"] is None
    # Missing classes do not create NaN values or a misleading AUC.
    small = prediction_metrics([0, 0], [0, 0], np.array([[1, 0, 0, 0], [1, 0, 0, 0]]))
    assert small["auc_roc_weighted"] is None
    json.dumps(small, allow_nan=False)


def test_notebook_agreement_is_explicit_and_does_not_hide_missing_metrics():
    evidence = {"saved_test_metrics": {"weighted_recall": 0.7962, "auc_roc_weighted": 0.8769}}
    assert notebook_comparison({"weighted_recall": 0.79622, "auc_roc_weighted": 0.87691}, evidence)["all_saved_metrics_match"]
    assert not notebook_comparison({"weighted_recall": 0.7921, "auc_roc_weighted": 0.8745}, evidence)["all_saved_metrics_match"]
    assert not notebook_comparison({"weighted_recall": 0.7962}, evidence)["all_saved_metrics_match"]


class FixedModel:
    n_features_in_ = 9
    classes_ = np.array([0, 1, 2, 3])

    def predict(self, values):
        return np.zeros(len(values), dtype=int)

    def predict_proba(self, values):
        return np.tile([0.7, 0.1, 0.1, 0.1], (len(values), 1))


@pytest.fixture
def evaluation_fixture(tmp_path, monkeypatch):
    dates = pd.to_datetime([f"{year}-01-0{day}" for year in [2022, 2023, 2024] for day in range(1, 5)])
    frame = pd.DataFrame({name: np.arange(12, dtype=float) for name in FEATURE_COLUMNS})
    frame["date"] = dates
    frame["risk_class"] = list(range(4)) * 3
    monkeypatch.setattr(proxy_evaluation, "prepare_dataset", lambda *args: (frame, {"merged_rows": 12}))
    notebook = tmp_path / "notebook.ipynb"
    notebook.write_text('{"cells":[]}', encoding="utf-8")
    scaler = proxy_evaluation.MinMaxScaler().fit(frame.loc[:3, list(FEATURE_COLUMNS)].to_numpy())
    joblib.dump(FixedModel(), tmp_path / "flood_model_final.joblib")
    joblib.dump(scaler, tmp_path / "scaler_final.joblib")
    joblib.dump(list(FEATURE_COLUMNS), tmp_path / "feature_cols_final.joblib")
    return tmp_path, notebook


def test_evaluation_keeps_validation_and_test_separate_and_never_modifies_artifacts(evaluation_fixture):
    root, notebook = evaluation_fixture
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.glob('*.joblib')}
    result = proxy_evaluation.evaluate_dataset(root / "rain.csv", root / "weather.csv", root, notebook)
    assert result["frozen_artifact"]["status"] == "evaluated"
    assert result["frozen_artifact"]["scaler_training_bounds_match"] is True
    assert set(result["frozen_artifact"]["metrics"]) == {"validation", "test"}
    assert result["splits"]["train"]["rows"] == result["splits"]["test"]["rows"] == 4
    assert result["baselines"]["training_majority_class"] == "Low"
    assert result["baselines"]["label_rule_agreement"] == 1
    assert result["street_level_accuracy_established"] is False
    assert result["forecast_lead_time_established"] is False
    assert before == {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.glob('*.joblib')}
    json.dumps(result, allow_nan=False)


def test_bad_snapshot_retains_data_findings_and_cli_writes_report_then_returns_failure(evaluation_fixture, monkeypatch):
    root, notebook = evaluation_fixture
    (root / "flood_model_final.joblib").write_bytes(b"invalid snapshot")
    output = root / "report.json"
    monkeypatch.setattr("sys.argv", ["evaluate_proxy_model", "--model-dir", str(root),
                                    "--notebook", str(notebook), "--output", str(output)])
    with pytest.raises(SystemExit) as failure:
        evaluate_proxy_model.main()
    assert failure.value.code == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["frozen_artifact"]["status"] == "unavailable"
    assert result["dataset"]["merged_rows"] == 12
    assert "reference_refit" not in result


def test_reference_refit_is_explicit_train_only_and_never_exports(evaluation_fixture):
    root, notebook = evaluation_fixture
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir()}
    result = proxy_evaluation.evaluate_dataset(root / "rain.csv", root / "weather.csv", root, notebook, reference_fit=True)
    assert result["reference_refit"]["training_rows"] == 4
    assert result["reference_refit"]["status"] == "diagnostic_only_not_exported"
    assert result["reference_refit"]["class_weights"] == {0: 1, 1: 1, 2: 2, 3: 2}
    assert before == {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir()}


def test_cli_cannot_overwrite_an_input_file(tmp_path, monkeypatch):
    source = tmp_path / "source.csv"
    source.write_bytes(b"original source bytes")
    monkeypatch.setattr("sys.argv", ["evaluate_proxy_model", "--chirps", str(source), "--output", str(source)])
    with pytest.raises(SystemExit) as failure:
        evaluate_proxy_model.main()
    assert failure.value.code == 2
    assert source.read_bytes() == b"original source bytes"
