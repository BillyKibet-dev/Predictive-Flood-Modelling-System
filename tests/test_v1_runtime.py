"""Strict native v1 contract and real frozen-reference parity; never fits a model."""
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import pytest

from src.modeling.v1.contract import (
    CLASS_NAMES, FEATURE_COLUMNS, V1ArtifactError, V1InputError,
    feature_fingerprint, validate_feature_row, validate_issue_context,
)
from src.modeling.v1.runtime import NativeV1Model, ROOT, package_manifest, verify_files
from src.scripts.package_model_v1 import install_files


@pytest.fixture
def row():
    # Explicit synthetic observations, solely for schema/failure-path tests.
    values = [2, 1, 4, 8, 4, 1, 2, 3, 4, 20, 65, 10, .3, .35, 4, .25, .5, .3, 0, 1]
    return dict(zip(FEATURE_COLUMNS, values))


def test_exact_order_no_unknown_or_missing_features(row):
    assert list(validate_feature_row(row)) == list(FEATURE_COLUMNS)
    assert len(feature_fingerprint(row)) == 64
    variants = [dict(reversed(list(row.items()))), {**row, "delta_water_level": 0},
                {key: value for key, value in row.items() if key != "ndvi"}]
    for invalid in variants:
        with pytest.raises(V1InputError):
            validate_feature_row(invalid)


@pytest.mark.parametrize("name", FEATURE_COLUMNS)
@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True, "0"])
def test_every_feature_must_be_a_real_finite_observation(row, name, value):
    with pytest.raises(V1InputError):
        validate_feature_row({**row, name: value})


@pytest.mark.parametrize("name,value", [
    ("chirps_daily_rain_mm", -1), ("wind_speed_mean_kmh", -1), ("humidity_mean_pct", 101),
    ("soil_moisture_mean_m3m3", 1.1), ("soil_moisture_eod_m3m3", -.1),
    ("slope_degrees", 91), ("ndvi", 1.1), ("impervious_fraction", -1),
    ("vegetation_fraction", 1.1), ("season_sin", 2), ("season_cos", 0),
    ("rainfall_3h_eod_mm", 5), ("meteo_daily_rain_mm", 5),
])
def test_physical_and_full_day_consistency(row, name, value):
    with pytest.raises(V1InputError):
        validate_feature_row({**row, name: value})


def test_issue_context_uses_next_nairobi_date_and_complete_day():
    issue = datetime(2024, 4, 30, 21, 0, tzinfo=timezone.utc)
    assert validate_issue_context(date(2024, 4, 30), issue).date() == date(2024, 5, 1)
    for invalid in [datetime(2024, 5, 1), datetime(2024, 4, 30, 20, 59, tzinfo=timezone.utc),
                    datetime(2024, 5, 2, 0, 0, tzinfo=timezone.utc)]:
        with pytest.raises(V1InputError):
            validate_issue_context(date(2024, 4, 30), invalid)


def test_missing_or_corrupt_package_is_unavailable_without_api_import(tmp_path, row):
    model = NativeV1Model(tmp_path, tmp_path / "missing-python")
    info = model.info()
    assert info["loaded"] is False and info["status"] == "MODEL_UNAVAILABLE"
    assert info["operational_status"] == "INSUFFICIENT_DATA"
    assert info["emergency_alert_delivery_enabled"] is False
    with pytest.raises(V1ArtifactError):
        model.predict(row)
    filename = next(iter(package_manifest()["files"]))
    (tmp_path / filename).write_bytes(b"corrupt native package")
    assert model.info()["loaded"] is False


@pytest.mark.parametrize("scores", [None, [], [[.25] * 4] * 2, [[.5, .5]],
                                   [[float("nan"), 0, 0, 1]], [[-.1, .2, .2, .7]],
                                   [[0, 0, 0, 2]], [[0, 0, 0, 0]], [[True, 0, 0, 0]]])
def test_invalid_output_shape_and_scores_fail_closed(row, scores, monkeypatch):
    model = NativeV1Model()
    monkeypatch.setattr(model, "_worker", lambda *args: {"scores": scores})
    with pytest.raises(V1ArtifactError):
        model.predict(row)


def test_class_order_and_identical_input_expectation_are_preserved(row, monkeypatch):
    model = NativeV1Model()
    monkeypatch.setattr(model, "_worker", lambda *args: {"scores": [[.1, .2, .3, .4]] * 2})
    results = model.predict_many([row, dict(row)])
    assert results[0] == results[1]
    assert list(results[0]["proxy_class_scores"]) == list(CLASS_NAMES)
    assert results[0]["risk_class"] == 3 and results[0]["risk_level"] == "Extreme"
    assert results[0]["model_class_score"] == .4
    assert "flood_probability" not in results[0]


def test_worker_timeout_and_private_errors_are_sanitized(monkeypatch, row):
    model = NativeV1Model(python_executable=Path(__import__('sys').executable))
    monkeypatch.setattr(model, "_verify", lambda: package_manifest())
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("private configuration must not escape", 30)
    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(V1ArtifactError) as error:
        model.predict(row)
    assert str(error.value) == "ISOLATED_MODEL_RUNTIME_FAILED"


def test_package_install_verifies_all_inputs_and_preserves_existing_versions(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.mkdir()
    (source / "model.json").write_bytes(b"trusted test bytes")
    expected = {"model.json": {"size_bytes": 18,
                "sha256": hashlib.sha256(b"trusted test bytes").hexdigest()}}
    install_files(source, destination, expected)
    install_files(source, destination, expected)
    assert (destination / "model.json").read_bytes() == b"trusted test bytes"
    (destination / "model.json").write_bytes(b"other research version")
    with pytest.raises(V1ArtifactError, match="DIFFERENT_VERSION"):
        install_files(source, destination, expected)
    assert (destination / "model.json").read_bytes() == b"other research version"
    (source / "model.json").write_bytes(b"corrupt")
    with pytest.raises(V1ArtifactError, match="INTEGRITY"):
        verify_files(source, expected)


def test_real_selected_native_artifact_matches_every_frozen_test_row():
    data = ROOT / "data/model_v1/NairobiFloodWatch_frozen_test_2024_2025.csv"
    model = NativeV1Model()
    if not data.is_file() or not model.python_executable.is_file():
        pytest.skip("Install the approved v1 research package/runtime to run real frozen parity")
    assert model.info()["loaded"] is True
    assert model.info()["runtime"]["xgboost"] == "3.1.3"
    frozen = pd.read_csv(data)
    reference = pd.read_csv(model.model_dir / "xgboost_test_predictions_proxy_only.csv")
    joined = frozen.merge(reference, on=["date", "target_date", "zone_id", "proxy_class_next_day"],
                          validate="one_to_one")
    assert len(joined) == 5848
    before = {name: hashlib.sha256((model.model_dir / name).read_bytes()).hexdigest()
              for name in package_manifest()["files"]}
    predictions = model.predict_many(joined.loc[:, list(FEATURE_COLUMNS)].to_dict("records"))
    scores = np.asarray([list(row["proxy_class_scores"].values()) for row in predictions])
    expected = joined[[f"score_{name.lower()}" for name in CLASS_NAMES]].to_numpy()
    np.testing.assert_allclose(scores, expected, rtol=1e-6, atol=1e-6)
    np.testing.assert_array_equal(scores.argmax(axis=1), joined.predicted_proxy_class)
    np.testing.assert_allclose(scores.sum(axis=1), 1, atol=1e-6)
    assert np.isfinite(scores).all() and (scores >= 0).all() and (scores <= 1).all()
    assert before == {name: hashlib.sha256((model.model_dir / name).read_bytes()).hexdigest()
                      for name in package_manifest()["files"]}
