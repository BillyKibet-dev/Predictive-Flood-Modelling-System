"""Load the Stage 2 XGBoost package and classify feature rows, with the Extreme guard.

Guard: the model may only output Extreme when the Stage 1 rule itself reaches at least
High; otherwise Extreme is reduced to High. Post-hoc on the held-out seasons this kept
the full High-or-above gain (CSI 0.524 vs rule 0.394) and removed all 24 Low->Extreme
false alarms (Extreme false-alarm ratio 0.57 -> 0.41, Extreme recall 0.32 -> 0.29).

The package is refused (fail closed, rule stays live) if the file hash, feature contract,
classes or XGBoost version differ from the manifest: a newer-to-older XGBoost load can
silently change scores (seen with the binary research model).
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import xgboost as xgb

from src.modeling.stage2.features import FEATURE_COLUMNS, FEATURE_VERSION

CLASSES = ("Low", "Moderate", "High", "Extreme")
HIGH, EXTREME = 2, 3
DEFAULT_DIR = Path(__file__).resolve().parents[3] / "models/stage2-rainfall-risk"


class Stage2ModelError(RuntimeError):
    pass


def guard(model_class: int, rule_level: int) -> tuple[int, bool]:
    """(final class, guard applied). Extreme needs the rule to reach High or above."""
    if model_class == EXTREME and rule_level < HIGH:
        return HIGH, True
    return model_class, False


class Stage2Model:
    def __init__(self, model_dir: Path | str = DEFAULT_DIR):
        self.model_dir = Path(model_dir)
        manifest_path = self.model_dir / "manifest.json"
        if not manifest_path.exists():
            raise Stage2ModelError(f"missing {manifest_path.name}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        model_path = self.model_dir / "model.json"
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        if digest != manifest.get("model_sha256"):
            raise Stage2ModelError("model checksum mismatch")
        if manifest.get("feature_version") != FEATURE_VERSION or tuple(manifest.get("feature_columns", ())) != FEATURE_COLUMNS:
            raise Stage2ModelError("feature contract mismatch")
        if tuple(manifest.get("classes", ())) != CLASSES:
            raise Stage2ModelError("class order mismatch")
        if manifest.get("xgboost_version") != xgb.__version__:
            raise Stage2ModelError(f"trained with XGBoost {manifest.get('xgboost_version')}, runtime is {xgb.__version__}")
        if not (manifest.get("decision") or {}).get("adopted"):
            raise Stage2ModelError("package was not adopted by its pre-declared evaluation")
        self.booster = xgb.Booster()
        self.booster.load_model(model_path)
        if tuple(self.booster.feature_names or ()) != FEATURE_COLUMNS:
            raise Stage2ModelError("model feature names differ from the contract")
        self.manifest = manifest
        self.version = f"stage2-xgb-{digest[:12]}"

    def classify(self, features: dict, rule_level: int) -> dict:
        row = np.array([[float(features[name]) for name in FEATURE_COLUMNS]], dtype=np.float32)
        if not np.isfinite(row).all():
            raise Stage2ModelError("non-finite model inputs")
        scores = self.booster.predict(xgb.DMatrix(row, feature_names=list(FEATURE_COLUMNS)))[0]
        if scores.shape != (4,) or not np.isclose(scores.sum(), 1.0, atol=1e-4) or (scores < 0).any():
            raise Stage2ModelError("invalid model output")
        raw = int(scores.argmax())
        final, applied = guard(raw, rule_level)
        return dict(model_class=raw, risk_level=final, guard_applied=applied,
                    scores={name: round(float(s), 6) for name, s in zip(CLASSES, scores)})
