"""Inspect trusted local model artefacts and saved notebook evidence, without running training.

No database connection, network request, or notebook execution is performed.
"""
import argparse
import ast
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re
import warnings

import joblib

from src.api.services.model_contract import PREDICTION_CONTEXT, SERVING_VERSION, validate_artifacts

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_FILES = ("flood_model_final.joblib", "scaler_final.joblib", "feature_cols_final.joblib")


def saved_notebook_evidence(path: Path) -> dict:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    feature_list, optional_soil, outputs, evaluation = None, False, [], ""
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        output = "".join("".join(item.get("text", [])) for item in cell.get("outputs", []))
        outputs.append(output)
        if "def evaluate(" in source and "TEST SET" in output:
            evaluation = output.split("TEST SET")[-1]
        try:
            tree = ast.parse(source)
        except SyntaxError:  # Colab shell/magic cells are deliberately not executed.
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "feature_cols" for target in node.targets):
                try:
                    feature_list = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
        optional_soil |= "feature_cols.append(sm_col)" in source
    date_range = re.search(r"Date range:\s*(\d{4}-\d{2}-\d{2}).*?(\d{4}-\d{2}-\d{2})", "\n".join(outputs))
    metrics = {}
    for name, pattern in {
        "weighted_recall": r"Weighted Recall:\s*([\d.]+)",
        "weighted_f1": r"Weighted F1-Score:\s*([\d.]+)",
        "auc_roc_weighted": r"AUC-ROC \(weighted\):\s*([\d.]+)",
    }.items():
        match = re.search(pattern, evaluation)
        if match:
            metrics[name] = float(match[1])
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "feature_list_in_code": feature_list,
        "conditional_soil_moisture_feature": optional_soil,
        "saved_merged_date_range": list(date_range.groups()) if date_range else None,
        "saved_test_metrics": metrics,
        "metrics_reproduced": False,
        "note": "Saved notebook outputs may be stale; no original training CSVs or training-time artefact manifest are packaged.",
    }


def audit_model(model_dir: Path, notebook_path: Path) -> dict:
    model_dir, notebook_path = Path(model_dir), Path(notebook_path)
    artefacts = {name: {"sha256": hashlib.sha256((model_dir / name).read_bytes()).hexdigest(),
                        "size_bytes": (model_dir / name).stat().st_size} for name in ARTIFACT_FILES}
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        model, scaler, features = (joblib.load(model_dir / name) for name in ARTIFACT_FILES)
    errors = []
    try:
        validate_artifacts(model, scaler, features)
    except ValueError as exc:
        errors.append(str(exc))
    compatibility = []
    for warning in captured:
        item = {"category": warning.category.__name__}
        if hasattr(warning.message, "original_sklearn_version"):
            item.update(serialized_version=warning.message.original_sklearn_version,
                        installed_version=warning.message.current_sklearn_version)
        else:
            item["message"] = "Library warning while loading serialized artefacts; review export compatibility."
        if item not in compatibility:
            compatibility.append(item)
    return {
        "audit_status": "review_required",
        "artifact_contract_valid": not errors,
        "contract_errors": errors,
        "prediction_context": dict(PREDICTION_CONTEXT),
        "serving_version": SERVING_VERSION,
        "artifacts": artefacts,
        "features": list(features),
        "feature_ranges": {name: {"training_min": float(low), "training_max": float(high)}
                           for name, low, high in zip(features, scaler.data_min_, scaler.data_max_)},
        "model_feature_count": int(model.n_features_in_),
        "scaler_feature_count": int(scaler.n_features_in_),
        "compatibility_warnings": compatibility,
        "environment": {"python": platform.python_version(), **{
            library: version(library) for library in ("numpy", "pandas", "scikit-learn", "xgboost", "joblib")}},
        "notebook_evidence": saved_notebook_evidence(notebook_path),
        "unresolved": [
            "No location, drainage, terrain or impervious-surface inputs in the final feature list.",
            "Labels are same-day rainfall/soil-moisture proxies, not observed local flood events.",
            "Training daily aggregates and CHIRPS rainfall differ from live hourly weather and partial-day rainfall.",
            "The runoff-change feature is derived from rainfall used to construct the proxy labels.",
            "Preprocessing occurs before the temporal split; training data is needed to assess contamination.",
            "No validated forecast lead time, street-level accuracy or probability calibration.",
            "Original data and a compatible re-export are required before metrics can be reproduced.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=PROJECT_ROOT / "models")
    parser.add_argument("--notebook", type=Path, default=PROJECT_ROOT / "notebooks/FloodHub.ipynb")
    parser.add_argument("--output", type=Path, help="Write JSON here instead of stdout")
    args = parser.parse_args()
    try:
        report = audit_model(args.model_dir, args.notebook)
        document = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(document, encoding="utf-8")
        else:
            print(document, end="")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        parser.exit(1, f"Model audit failed: {exc}\n")
    if not report["artifact_contract_valid"]:
        parser.exit(1, "Model artefacts do not match the input contract.\n")


if __name__ == "__main__":
    main()
