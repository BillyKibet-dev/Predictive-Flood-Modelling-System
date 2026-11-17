"""The original 9-feature model loads from JSON (no pickle, no version warnings) and is checked."""
import shutil
import warnings
from pathlib import Path

import pytest

from src.api.services.ml_service import MLService, load_json_artifacts
from src.api.services.model_contract import FEATURE_COLUMNS

EXPORT = Path(__file__).resolve().parents[1] / "models/legacy-v2"
ROW = dict(precipitation_sum=12.0, rain_7d=40.0, rain_3d=20.0, temperature_2m=21.0, relative_humidity_2m=80.0,
           soil_moisture_0_to_7cm=0.3, month=4, day_of_year=110, is_long_rains=1, is_short_rains=0)


def test_loads_without_version_warnings_and_predicts_four_classes():
    with warnings.catch_warnings():
        warnings.simplefilter("error")   # any InconsistentVersionWarning/UserWarning fails the test
        service = MLService()
    assert service.is_loaded and service.feature_cols == list(FEATURE_COLUMNS)
    row = {name: ROW.get(name, 1.0) for name in FEATURE_COLUMNS}
    result = service.predict(row)
    assert set(result["all_probabilities"]) == {"Low", "Moderate", "High", "Extreme"}
    assert abs(sum(result["all_probabilities"].values()) - 1) < 1e-5
    assert result["risk_level"] == max(result["all_probabilities"], key=result["all_probabilities"].get)


def test_export_records_exact_equivalence_with_the_pickles():
    import json
    manifest = json.loads((EXPORT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["equivalence"]["max_abs_probability_difference"] <= 1e-6
    assert manifest["equivalence"]["same_class_every_row"] is True


@pytest.mark.parametrize("name", ["model.json", "scaler.json", "features.json"])
def test_a_changed_file_is_refused(tmp_path, name):
    copy = tmp_path / "legacy"
    shutil.copytree(EXPORT, copy)
    with open(copy / name, "a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="manifest"):
        load_json_artifacts(copy)
