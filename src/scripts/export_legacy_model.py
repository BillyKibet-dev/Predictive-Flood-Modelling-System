"""Convert the original pickled model (models/*_final.joblib) to version-independent JSON.

The pickles were saved with scikit-learn 1.6.1 and a newer XGBoost than the API uses, so
loading them warns and is not guaranteed to behave the same; unpickling can also run code.
This writes models/legacy-v2/ (XGBoost's own JSON format, the scaler's numbers and the
feature order) and proves the converted model gives the same probabilities on 5,000 inputs
spread over the scaler's range before anything is written. The pickles are left untouched.

    python -m src.scripts.export_legacy_model
"""
import hashlib
import json
from pathlib import Path
import warnings

import joblib
import numpy as np
import xgboost as xgb

from src.api.services.model_contract import FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "models"
OUT = ROOT / "models/legacy-v2"
TOLERANCE = 1e-6


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scale(params: dict, rows: np.ndarray) -> np.ndarray:
    """MinMaxScaler.transform, from its saved numbers (clip=False, as fitted)."""
    return rows * np.asarray(params["scale"]) + np.asarray(params["min"])


def main():
    names = ("flood_model_final.joblib", "scaler_final.joblib", "feature_cols_final.joblib")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the version warnings are why we are converting
        model, scaler, features = (joblib.load(SOURCE / n) for n in names)
    if list(features) != list(FEATURE_COLUMNS) or list(model.classes_) != [0, 1, 2, 3]:
        raise SystemExit("Source artifacts do not match the input contract; nothing written.")
    if getattr(scaler, "clip", False):
        raise SystemExit("Scaler uses clipping, which this export does not reproduce; nothing written.")
    params = dict(feature_range=list(scaler.feature_range), data_min=scaler.data_min_.tolist(),
                  data_max=scaler.data_max_.tolist(), scale=scaler.scale_.tolist(), min=scaler.min_.tolist())

    booster = model.get_booster()
    OUT.mkdir(parents=True, exist_ok=True)
    tmp_model = OUT / "model.tmp.json"  # the .json suffix selects XGBoost's JSON format
    booster.save_model(tmp_model)
    converted = xgb.Booster()
    converted.load_model(tmp_model)

    # Equivalence: inputs across (and 10% beyond) the training range, plus the range edges.
    rng = np.random.default_rng(42)
    low, high = scaler.data_min_, scaler.data_max_
    span = high - low
    rows = rng.uniform(low - 0.1 * span, high + 0.1 * span, size=(5000, len(features)))
    rows = np.vstack([rows, low, high])
    expected = model.predict_proba(scaler.transform(rows))
    actual = converted.predict(xgb.DMatrix(scale(params, rows).astype(np.float32), feature_names=booster.feature_names))
    difference = float(np.abs(expected - actual).max())
    if difference > TOLERANCE or (expected.argmax(1) != actual.argmax(1)).any():
        tmp_model.unlink()
        raise SystemExit(f"Converted model differs (max {difference:.2e}); nothing written.")

    tmp_model.replace(OUT / "model.json")
    (OUT / "scaler.json").write_text(json.dumps(params, indent=1), encoding="utf-8")
    (OUT / "features.json").write_text(json.dumps(list(features)), encoding="utf-8")
    manifest = dict(
        purpose="Original 9-feature flood-risk model (legacy pipeline), converted from pickles to JSON.",
        source_sha256={n: sha256(SOURCE / n) for n in names},
        files_sha256={n: sha256(OUT / n) for n in ("model.json", "scaler.json", "features.json")},
        exported_with=dict(xgboost=xgb.__version__, scikit_learn=__import__("sklearn").__version__),
        booster_feature_names=booster.feature_names,
        equivalence=dict(rows=len(rows), max_abs_probability_difference=difference, tolerance=TOLERANCE,
                         same_class_every_row=True),
    )
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"Exported to {OUT.relative_to(ROOT)}; max probability difference {difference:.2e} over {len(rows)} rows.")


if __name__ == "__main__":
    main()
