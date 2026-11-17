"""Isolated native-XGBoost worker; stdout is always one JSON document."""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import xgboost as xgb

from src.modeling.binary_rainfall.contract import FEATURE_COLUMNS

EXPECTED_XGBOOST = "3.1.3"


def fail(code):
    print(json.dumps({"status": "ERROR", "code": code}), flush=True)
    return 1


def main():
    try:
        request = json.loads(sys.stdin.read())
        path = Path(request["model_path"]).resolve()
        expected_hash = request["expected_sha256"]
        rows = request["rows"]
        if xgb.__version__ != EXPECTED_XGBOOST:
            return fail("XGBOOST_RUNTIME_VERSION_MISMATCH")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            return fail("MODEL_HASH_MISMATCH")
        native = json.loads(raw)
        learner = native["learner"]
        if (tuple(learner["feature_names"]) != FEATURE_COLUMNS
                or learner["objective"]["name"] != "binary:logistic"
                or int(learner["learner_model_param"]["num_feature"]) != len(FEATURE_COLUMNS)):
            return fail("NATIVE_MODEL_CONTRACT_MISMATCH")
        if tuple(native.get("version", ())) != (3, 1, 3):
            return fail("NATIVE_MODEL_VERSION_MISMATCH")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 40:
            return fail("INVALID_ROW_COUNT")
        matrix = []
        for row in rows:
            if tuple(row) != FEATURE_COLUMNS:
                return fail("FEATURE_ORDER_MISMATCH")
            values = [row[name] for name in FEATURE_COLUMNS]
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
                return fail("INVALID_FEATURE_VALUE")
            matrix.append(values)
        model = xgb.Booster()
        model.load_model(str(path))
        scores = model.predict(xgb.DMatrix(np.asarray(matrix, dtype=np.float64), feature_names=list(FEATURE_COLUMNS)))
        if len(scores) != len(rows) or any(not math.isfinite(float(score)) or not 0 <= float(score) <= 1 for score in scores):
            return fail("INVALID_MODEL_OUTPUT")
        print(json.dumps({"status": "OK", "runtime_xgboost": xgb.__version__,
                          "scores": [float(value) for value in scores]}), flush=True)
        return 0
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return fail("WORKER_INPUT_OR_MODEL_ERROR")


if __name__ == "__main__":
    raise SystemExit(main())
