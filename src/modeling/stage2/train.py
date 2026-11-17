"""Stage 2: does a small XGBoost beat the Stage 1 rule on genuinely live-available inputs?

    python -m src.modeling.stage2.train

Data: archived ECMWF IFS 00 UTC runs (issue day I) + IMERG Early observed days + CHIRPS
v1 labels for target I+1, 8 zones, Mar 2024 - Sep 2026.

Pre-declared protocol (fixed before any result was seen):
* Validation: leave-one-season-out over 10 seasonal blocks (MAM, JJAS, OND, JF by year),
  plus a forward check training only on earlier blocks.
* Contenders: Stage 1 rule (live), old tomorrow-only rule, XGBoost with fixed
  hyper-parameters (no tuning), balanced class weights, arg-max class.
* Primary metric: zone-day High-or-above critical success index (CSI).
* Adoption: XGBoost replaces the rule only if mean CSI gain > 0, the 95 % date-cluster
  bootstrap interval of the gain is entirely above 0, and Extreme recall falls by no more
  than 0.05. Otherwise the rule stays live and XGBoost is reported as an experiment.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import f1_score
from sklearn.utils.class_weight import compute_sample_weight

from src.modeling.stage2.dataset import build_table
from src.modeling.stage2.features import FEATURE_COLUMNS, FEATURE_VERSION

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "models/stage2-rainfall-risk"
REPORT = ROOT / "data/stage2/evaluation.json"
CLASSES = ("Low", "Moderate", "High", "Extreme")
PARAMS = dict(objective="multi:softprob", num_class=4, n_estimators=300, learning_rate=0.05, max_depth=3,
              min_child_weight=5, subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0, tree_method="hist",
              random_state=42, n_jobs=4)
BOOTSTRAP = 2000
EXTREME_RECALL_TOLERANCE = 0.05


def season(ts: pd.Timestamp) -> str:
    m = ts.month
    name = "MAM" if m in (3, 4, 5) else "JJAS" if m in (6, 7, 8, 9) else "OND" if m in (10, 11, 12) else "JF"
    return f"{ts.year}-{name}"


def events(obs, pred):
    hits = int((obs & pred).sum()); misses = int((obs & ~pred).sum()); false = int((~obs & pred).sum())
    total = hits + misses + false
    return dict(hits=hits, misses=misses, false_alarms=false,
                pod=hits / (hits + misses) if hits + misses else None,
                far=false / (hits + false) if hits + false else None,
                csi=hits / total if total else None)


def scores(frame: pd.DataFrame, column: str) -> dict:
    y, p = frame["label"].to_numpy(), frame[column].to_numpy()
    by_date = frame.groupby("target_date")[["label", column]].max()
    return dict(rows=len(frame), macro_f1=float(f1_score(y, p, labels=[0, 1, 2, 3], average="macro", zero_division=0)),
                high_or_above=events(y >= 2, p >= 2), extreme=events(y == 3, p == 3),
                date_level_high_or_above=events(by_date["label"].to_numpy() >= 2, by_date[column].to_numpy() >= 2))


def csi(frame, column):
    obs, pred = frame["label"].to_numpy() >= 2, frame[column].to_numpy() >= 2
    hits = (obs & pred).sum(); total = (obs | pred).sum()
    return hits / total if total else 0.0


def fit(train: pd.DataFrame) -> xgb.XGBClassifier:
    model = xgb.XGBClassifier(**PARAMS)
    model.fit(train[list(FEATURE_COLUMNS)], train["label"], sample_weight=compute_sample_weight("balanced", train["label"]))
    return model


def predict(model, frame) -> np.ndarray:
    return model.predict_proba(frame[list(FEATURE_COLUMNS)]).argmax(axis=1)


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    table, skipped = build_table()
    table["season"] = table["target_date"].map(season)
    table["rule"] = table["rule_class_level"].astype(int)
    table["old_rule"] = table["rule_tomorrow_level"].astype(int)
    blocks = sorted(table["season"].unique(), key=lambda s: (int(s[:4]), ["JF", "MAM", "JJAS", "OND"].index(s[5:])))
    print(f"{len(table):,} rows, {table.issue_date.nunique()} issue days, {len(blocks)} season blocks; skipped {skipped}")
    print("label support:", dict(zip(CLASSES, np.bincount(table.label, minlength=4).tolist())))
    print("IMERG versions:", table.imerg_version.value_counts().to_dict())

    # Leave-one-season-out (primary) and forward-only (secondary) out-of-sample predictions.
    table["xgb_loso"] = -1
    table["xgb_forward"] = -1
    for i, block in enumerate(blocks):
        held = table["season"] == block
        if table.loc[~held, "label"].nunique() == 4:
            table.loc[held, "xgb_loso"] = predict(fit(table[~held]), table[held])
        earlier = table["season"].isin(blocks[:i])
        if i >= 3 and table.loc[earlier, "label"].nunique() == 4:
            table.loc[held, "xgb_forward"] = predict(fit(table[earlier]), table[held])

    loso = table[table["xgb_loso"] >= 0]
    forward = table[table["xgb_forward"] >= 0]
    results = {
        "leave_one_season_out": {name: scores(loso, col) for name, col in
                                 (("stage1_rule", "rule"), ("old_tomorrow_rule", "old_rule"), ("xgboost", "xgb_loso"))},
        "forward_only": {name: scores(forward, col) for name, col in
                         (("stage1_rule", "rule"), ("old_tomorrow_rule", "old_rule"), ("xgboost", "xgb_forward"))},
        "by_season": {block: {name: scores(g, col)["high_or_above"]["csi"] for name, col in
                              (("stage1_rule", "rule"), ("xgboost", "xgb_loso"))}
                      for block, g in loso.groupby("season")},
    }

    # Date-cluster bootstrap of the CSI gain (XGBoost - rule), leave-one-season-out predictions.
    rng = np.random.default_rng(412)
    obs = loso["label"].to_numpy() >= 2
    per_date = pd.DataFrame({"target_date": loso["target_date"].to_numpy()})
    for name, column in (("xgb", "xgb_loso"), ("rule", "rule")):
        pred = loso[column].to_numpy() >= 2
        per_date[f"{name}_hits"], per_date[f"{name}_union"] = obs & pred, obs | pred
    per_date = per_date.groupby("target_date").sum()          # one row per date: a resampling cluster
    counts = per_date.to_numpy(dtype=float)
    gains = []
    for _ in range(BOOTSTRAP):
        s = counts[rng.integers(0, len(counts), size=len(counts))].sum(axis=0)
        xgb_csi = s[0] / s[1] if s[1] else 0.0
        rule_csi = s[2] / s[3] if s[3] else 0.0
        gains.append(xgb_csi - rule_csi)
    gain = csi(loso, "xgb_loso") - csi(loso, "rule")
    low, high = np.percentile(gains, [2.5, 97.5])
    ext = results["leave_one_season_out"]
    extreme_drop = (ext["stage1_rule"]["extreme"]["pod"] or 0) - (ext["xgboost"]["extreme"]["pod"] or 0)
    adopted = bool(gain > 0 and low > 0 and extreme_drop <= EXTREME_RECALL_TOLERANCE)
    decision = dict(primary_metric="zone-day High-or-above CSI, leave-one-season-out", csi_gain=float(gain),
                    bootstrap_95=[float(low), float(high)], extreme_recall_drop=float(extreme_drop),
                    adopted=adopted, live_method="stage2_xgboost" if adopted else "stage1_rule")

    for name, block in (("LEAVE-ONE-SEASON-OUT", ext), ("FORWARD-ONLY", results["forward_only"])):
        print(f"\n{name}")
        for model, s in block.items():
            h, e, dl = s["high_or_above"], s["extreme"], s["date_level_high_or_above"]
            print(f"  {model:<18} macroF1={s['macro_f1']:.3f} | High+ POD={h['pod']:.2f} FAR={h['far']:.2f} CSI={h['csi']:.3f}"
                  f" | Extreme POD={e['pod']:.2f} FAR={(e['far'] if e['far'] is not None else float('nan')):.2f}"
                  f" | date-level High+ CSI={dl['csi']:.3f}")
    print("\nby season (High+ CSI rule vs xgboost):")
    for block, v in results["by_season"].items():
        print(f"  {block:<10} rule={v['stage1_rule'] if v['stage1_rule'] is not None else float('nan'):.3f}  xgb={v['xgboost'] if v['xgboost'] is not None else float('nan'):.3f}")
    print(f"\nDECISION: CSI gain {gain:+.3f} (95% {low:+.3f}..{high:+.3f}), Extreme recall drop {extreme_drop:+.3f}"
          f" -> {'ADOPT XGBoost' if adopted else 'KEEP Stage 1 rule'}")

    # Final model on all data (kept for the record and for use if adopted).
    # A rejected retrain never replaces the live package: it is kept separately for review.
    out = OUT if adopted else OUT.with_name(OUT.name + "-rejected")
    out.mkdir(parents=True, exist_ok=True)
    final = fit(table)
    model_path = out / "model.json"
    final.save_model(model_path)
    manifest = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), feature_version=FEATURE_VERSION,
                    feature_columns=list(FEATURE_COLUMNS), classes=list(CLASSES), params=PARAMS,
                    xgboost_version=xgb.__version__, model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
                    training_rows=len(table), issue_days=[str(table.issue_date.min().date()), str(table.issue_date.max().date())],
                    label="v1 CHIRPS rule on target day (40/20/5 mm daily, 150/80/25 mm 7-day)",
                    inputs="ECMWF IFS 00 UTC single run (Open-Meteo) + NASA IMERG Early daily, no terrain",
                    decision=decision)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    REPORT.write_text(json.dumps(dict(protocol=__doc__, skipped=skipped, decision=decision, **results), indent=2, default=str),
                      encoding="utf-8")
    table.to_csv(ROOT / "data/stage2/predictions_out_of_sample.csv", index=False)
    print(f"\nwrote {REPORT.relative_to(ROOT)} and {out.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
