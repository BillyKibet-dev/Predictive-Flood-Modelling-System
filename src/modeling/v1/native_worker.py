"""Small isolated native worker. No API imports, joblib, network or database access."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        import numpy as np
        import xgboost as xgb

        if xgb.__version__ != "3.1.3":
            raise RuntimeError("UNVERIFIED_RUNTIME_VERSION")
        blob = args.model.read_bytes()
        if hashlib.sha256(blob).hexdigest() != args.sha256:
            raise ValueError("ARTIFACT_HASH_MISMATCH")
        model = xgb.Booster(params={"nthread": 2})
        # The immutable verified buffer, not another file read, is deserialized.
        model.load_model(bytearray(blob))
        request = json.loads(sys.stdin.read(32_000_001))
        if request.get("command") not in ("inspect", "predict"):
            raise ValueError("INVALID_WORKER_COMMAND")
        result = {"runtime": {"python": platform.python_version(), "xgboost": xgb.__version__,
                              "numpy": np.__version__},
                  "feature_names": model.feature_names, "feature_count": model.num_features(),
                  "rounds": model.num_boosted_rounds()}
        if request["command"] == "predict":
            rows = request.get("rows")
            if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
                raise ValueError("INVALID_BATCH_SIZE")
            values = np.asarray(rows, dtype=np.float64)
            if values.shape != (len(rows), 20) or not np.isfinite(values).all():
                raise ValueError("INVALID_FEATURE_MATRIX")
            scores = model.predict(xgb.DMatrix(values, feature_names=model.feature_names))
            result["scores"] = scores.tolist()
        print(json.dumps(result, allow_nan=False, separators=(",", ":")))
    except Exception as exc:
        # Never emit arbitrary provider/model error strings or local paths.
        print(json.dumps({"error": "NATIVE_MODEL_UNAVAILABLE", "error_type": type(exc).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
