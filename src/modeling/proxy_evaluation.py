"""Reconstruct the notebook's daily proxy task; never promote or export a model."""
import hashlib
from importlib.metadata import version
from pathlib import Path
import platform
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, roc_auc_score
from sklearn.preprocessing import MinMaxScaler
from sklearn.utils.class_weight import compute_class_weight
from xgboost import XGBClassifier

from src.api.services.model_contract import FEATURE_COLUMNS, scs_wl, validate_artifacts
from src.scripts.audit_model import ARTIFACT_FILES, saved_notebook_evidence

LABELS = ("Low", "Moderate", "High", "Extreme")
PROVENANCE_PATH = Path(__file__).resolve().parents[2] / "data/provenance/training_sources.candidate.json"
WEATHER_COLUMNS = ("temperature_2m", "relative_humidity_2m", "precipitation",
                   "wind_speed_10m", "soil_moisture_0_to_7cm")
TRAIN_END = pd.Timestamp("2022-12-31")
VALIDATION_END = pd.Timestamp("2023-12-31")
REFERENCE_PARAMETERS = {
    "learning_rate": 0.05, "max_depth": 7, "min_child_weight": 1,
    "n_estimators": 300, "subsample": 0.8, "gamma": 0,
    "colsample_bytree": 0.8, "random_state": 42,
}


def fingerprint(path: Path) -> dict:
    path = Path(path)
    return {"filename": path.name, "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def inspect_source(path: Path, kind: str) -> tuple[pd.DataFrame, dict]:
    """Fail before evaluation on gaps, duplicates, invalid dates or missing values."""
    if kind not in ("chirps", "weather"):
        raise ValueError("Unknown source kind")
    path = Path(path)
    frame = pd.read_csv(path)
    time_column = "system:index" if kind == "chirps" else "time"
    required = ("precipitation",) if kind == "chirps" else WEATHER_COLUMNS
    if not len(frame) or not {time_column, *required}.issubset(frame.columns):
        raise ValueError(f"{path.name}: missing rows or required columns")
    stamps = pd.to_datetime(frame[time_column].astype(str),
                            format="%Y%m%d" if kind == "chirps" else "%Y-%m-%dT%H:%M",
                            errors="coerce")
    if stamps.isna().any() or stamps.duplicated().any() or not stamps.is_monotonic_increasing:
        raise ValueError(f"{path.name}: invalid, duplicate or unordered timestamps")
    if kind == "chirps" and "date" in frame:
        dates = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="coerce")
        if not dates.equals(stamps):
            raise ValueError(f"{path.name}: date and system:index disagree")
    expected = pd.date_range(stamps.iloc[0], stamps.iloc[-1], freq="D" if kind == "chirps" else "h")
    if len(expected.difference(stamps)):
        raise ValueError(f"{path.name}: missing timestamps")
    if kind == "weather":
        if stamps.dt.minute.any() or not stamps.groupby(stamps.dt.normalize()).size().eq(24).all():
            raise ValueError(f"{path.name}: every weather day must contain all 24 hours")
    statistics = {}
    for name in required:
        values = pd.to_numeric(frame[name], errors="coerce")
        if not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ValueError(f"{path.name}: {name} contains missing or non-finite values")
        if name in ("precipitation", "wind_speed_10m") and (values < 0).any():
            raise ValueError(f"{path.name}: {name} contains negative values")
        if name == "relative_humidity_2m" and not values.between(0, 100).all():
            raise ValueError(f"{path.name}: invalid humidity")
        if name == "soil_moisture_0_to_7cm" and not values.between(0, 1).all():
            raise ValueError(f"{path.name}: invalid soil moisture")
        frame[name] = values
        statistics[name] = {"minimum": float(values.min()), "maximum": float(values.max()),
                            "mean": float(values.mean()), "missing_values": 0}
    frame = frame.loc[:, list(required)].copy()
    frame.insert(0, "date", stamps)
    profile = {**fingerprint(path), "kind": kind, "rows": len(frame),
               "start": stamps.iloc[0].isoformat(), "end": stamps.iloc[-1].isoformat(),
               "frequency": "daily" if kind == "chirps" else "hourly",
               "missing_timestamps": 0, "duplicate_timestamps": 0,
               "imputed_values": 0, "statistics": statistics}
    return frame, profile


def assign_proxy_labels(rainfall, seven_day_rainfall, soil_moisture) -> np.ndarray:
    """Same-day notebook thresholds; these labels are not observed flood events."""
    rain, week, soil = (np.asarray(values, dtype=float) for values in (rainfall, seven_day_rainfall, soil_moisture))
    return np.select([(rain >= 40) | (week >= 150), (rain >= 20) | (week >= 80),
                      (rain >= 5) | (week >= 25) | (soil > 0.70)], [3, 2, 1], default=0)


def prepare_dataset(chirps_path: Path, weather_path: Path) -> tuple[pd.DataFrame, dict]:
    rain, rain_profile = inspect_source(chirps_path, "chirps")
    weather, weather_profile = inspect_source(weather_path, "weather")
    rain = rain.rename(columns={"precipitation": "chirps_rainfall_mm"})
    hourly = weather.set_index("date")
    daily = hourly.drop(columns="precipitation").resample("D").mean()
    # Sum hourly depths for source comparison; notebook's mean precipitation is not a model input.
    daily["open_meteo_rainfall_mm"] = hourly.precipitation.resample("D").sum()
    daily = daily.reset_index()
    frame = rain.merge(daily, on="date", how="inner", validate="one_to_one")
    if frame.empty:
        raise ValueError("The source files have no overlapping dates")
    frame["rainfall_7day"] = frame.chirps_rainfall_mm.rolling(7, min_periods=1).sum()
    levels = pd.Series([scs_wl(r, sm=sm) for r, sm in
                        zip(frame.chirps_rainfall_mm, frame.soil_moisture_0_to_7cm)])
    frame["delta_water_level"] = levels.diff().fillna(0)
    frame["month"] = frame.date.dt.month
    frame["day_of_year"] = frame.date.dt.dayofyear
    frame["is_long_rains"] = frame.month.isin([3, 4, 5]).astype(int)
    frame["is_short_rains"] = frame.month.isin([10, 11, 12]).astype(int)
    frame["risk_class"] = assign_proxy_labels(frame.chirps_rainfall_mm, frame.rainfall_7day,
                                               frame.soil_moisture_0_to_7cm)
    excluded_weather = daily.loc[~daily.date.isin(frame.date), "date"]
    excluded_rain = rain.loc[~rain.date.isin(frame.date), "date"]
    correlation = (frame.chirps_rainfall_mm.corr(frame.open_meteo_rainfall_mm)
                   if frame.chirps_rainfall_mm.nunique() > 1 and frame.open_meteo_rainfall_mm.nunique() > 1
                   else None)
    summary = {"sources": {"chirps": rain_profile, "weather": weather_profile},
               "merged_rows": len(frame), "start": frame.date.min().date().isoformat(),
               "end": frame.date.max().date().isoformat(),
               "excluded_weather_days": [value.date().isoformat() for value in excluded_weather],
               "excluded_chirps_days": [value.date().isoformat() for value in excluded_rain],
               "class_counts": class_counts(frame.risk_class),
               "rainfall_daily_correlation": float(correlation) if correlation is not None and np.isfinite(correlation) else None,
               "same_calendar_date_join": True, "accumulation_windows_reconciled": False,
               "imputation_performed": False}
    return frame, summary


def class_counts(values) -> dict:
    counts = pd.Series(values).value_counts()
    return {label: int(counts.get(index, 0)) for index, label in enumerate(LABELS)}


def chronological_splits(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    splits = {"train": frame[frame.date <= TRAIN_END],
              "validation": frame[(frame.date > TRAIN_END) & (frame.date <= VALIDATION_END)],
              "test": frame[frame.date > VALIDATION_END]}
    if any(part.empty for part in splits.values()):
        raise ValueError("Train, validation and test periods must all contain rows")
    return splits


def prediction_metrics(truth, prediction, probabilities=None) -> dict:
    truth, prediction = np.asarray(truth), np.asarray(prediction)
    report = classification_report(truth, prediction, labels=list(range(4)), target_names=LABELS,
                                   output_dict=True, zero_division=0)
    auc = None
    if probabilities is not None and len(np.unique(truth)) == 4:
        auc = float(roc_auc_score(truth, probabilities, multi_class="ovr", average="weighted"))
    return {"rows": len(truth), "class_counts": class_counts(truth),
            "accuracy": float(accuracy_score(truth, prediction)),
            "weighted_recall": float(report["weighted avg"]["recall"]),
            "weighted_f1": float(report["weighted avg"]["f1-score"]),
            "macro_recall": float(report["macro avg"]["recall"]),
            "auc_roc_weighted": auc,
            "per_class": {name: {key: int(value) if key == "support" else float(value)
                                  for key, value in report[name].items()} for name in LABELS},
            "confusion_matrix": confusion_matrix(truth, prediction, labels=list(range(4))).tolist(),
            "prediction_sha256": hashlib.sha256(prediction.astype("<i8").tobytes()).hexdigest()}


def evaluate_estimator(model, scaler, splits: dict) -> dict:
    result = {}
    for name in ("validation", "test"):
        part = splits[name]
        scaled = scaler.transform(part.loc[:, list(FEATURE_COLUMNS)].to_numpy())
        result[name] = prediction_metrics(part.risk_class, model.predict(scaled), model.predict_proba(scaled))
    return result


def notebook_comparison(metrics: dict, evidence: dict) -> dict:
    saved = evidence.get("saved_test_metrics", {})
    matches = {name: round(metrics[name], 4) == value for name, value in saved.items()
               if metrics.get(name) is not None}
    return {"saved_test_metrics": saved, "matches_at_four_decimal_places": matches,
            "all_saved_metrics_match": bool(matches) and len(matches) == len(saved) and all(matches.values())}


def evaluate_dataset(chirps_path: Path, weather_path: Path, model_dir: Path,
                     notebook_path: Path, reference_fit: bool = False) -> dict:
    """Evaluate trusted frozen artefacts; optionally refit the documented recipe in memory."""
    frame, dataset = prepare_dataset(chirps_path, weather_path)
    splits = chronological_splits(frame)
    notebook = saved_notebook_evidence(notebook_path)
    majority_class = int(splits["train"].risk_class.mode().iloc[0])
    report = {
        "evaluation_recipe": "notebook_v2_daily_proxy_replay_v1",
        "target": "same_day_rainfall_soil_moisture_proxy_class",
        "street_level_accuracy_established": False, "forecast_lead_time_established": False,
        "source_provenance": {"status": "user_supplied_candidate_scripts_export_execution_unverified",
                              "candidate_manifest": fingerprint(PROVENANCE_PATH)},
        "dataset": dataset,
        "splits": {name: {"rows": len(part), "start": part.date.min().date().isoformat(),
                          "end": part.date.max().date().isoformat(), "class_counts": class_counts(part.risk_class)}
                   for name, part in splits.items()},
        "environment": {"python": platform.python_version(), "platform": platform.system(),
                        "machine": platform.machine(), **{library: version(library) for library in
                        ("numpy", "pandas", "scipy", "scikit-learn", "xgboost", "joblib")}},
        "artifacts": {name: fingerprint(Path(model_dir) / name) for name in ARTIFACT_FILES},
        "notebook": {"sha256": notebook["sha256"], "saved_test_metrics": notebook["saved_test_metrics"]},
        "baselines": {
            "training_majority_class": LABELS[majority_class],
            "majority_class": {name: prediction_metrics(part.risk_class, np.full(len(part), majority_class))
                               for name, part in splits.items() if name != "train"},
            "label_rule_agreement": 1.0,
            "label_rule_note": "The threshold rule constructs the target. Its perfect agreement is tautological, not evidence of forecasting skill.",
        },
        "limitations": [
            "Labels and runoff-change inputs depend on the same rainfall source; outcomes are not observed floods.",
            "Replay uses full daily aggregates and does not validate live hourly/partial-day inputs.",
            "CHIRPS UTC image-date keys and Nairobi weather calendar days are joined as in the notebook; accumulation windows remain unverified.",
            "Single-point source scripts do not establish sub-county or street-level coverage.",
            "The original training-time environment and artefact provenance are not fully recorded.",
        ],
    }
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        try:
            model, scaler, features = (joblib.load(Path(model_dir) / name) for name in ARTIFACT_FILES)
            validate_artifacts(model, scaler, features)
            metrics = evaluate_estimator(model, scaler, splits)
            train_values = splits["train"].loc[:, list(FEATURE_COLUMNS)]
            frozen = {"status": "evaluated", "metrics": metrics,
                      "scaler_training_bounds_match": bool(
                          np.allclose(train_values.min().to_numpy(), scaler.data_min_) and
                          np.allclose(train_values.max().to_numpy(), scaler.data_max_)),
                      "notebook_comparison": notebook_comparison(metrics["test"], notebook)}
        except Exception as exc:  # Keep data findings available even when legacy snapshots cannot load.
            frozen = {"status": "unavailable", "error_type": type(exc).__name__,
                      "error": "Frozen model could not be loaded or evaluated in this environment"}
    frozen["compatibility_warning_categories"] = sorted({warning.category.__name__ for warning in captured})
    if frozen["status"] == "evaluated" and captured:
        frozen["status"] = "evaluated_with_compatibility_warnings"
    report["frozen_artifact"] = frozen
    if reference_fit:
        train = splits["train"]
        classes = np.unique(train.risk_class)
        if list(classes) != [0, 1, 2, 3]:
            raise ValueError("Reference fitting requires all four classes in training")
        scaler = MinMaxScaler().fit(train.loc[:, list(FEATURE_COLUMNS)].to_numpy())
        weights = compute_class_weight("balanced", classes=classes, y=train.risk_class.to_numpy())
        class_weights = {int(cls): float(weight) * (2 if cls >= 2 else 1) for cls, weight in zip(classes, weights)}
        model = XGBClassifier(**REFERENCE_PARAMETERS, eval_metric="mlogloss", n_jobs=-1)
        model.fit(scaler.transform(train.loc[:, list(FEATURE_COLUMNS)].to_numpy()), train.risk_class.to_numpy(),
                  sample_weight=np.array([class_weights[int(cls)] for cls in train.risk_class]))
        metrics = evaluate_estimator(model, scaler, splits)
        report["reference_refit"] = {"status": "diagnostic_only_not_exported",
                                     "parameters": {**REFERENCE_PARAMETERS, "n_jobs": -1},
                                     "training_rows": len(train),
                                     "class_weights": class_weights, "metrics": metrics,
                                     "notebook_comparison": notebook_comparison(metrics["test"], notebook)}
    return report
