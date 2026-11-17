"""Assemble the Stage 2 training table: archived IFS runs + IMERG Early + CHIRPS v1 labels.

One row per (issue day I, zone). Target T = I+1. The label is the unchanged v1 rule on
CHIRPS: Extreme if CHIRPS(T) >= 40 or 7-day CHIRPS ending T >= 150; High 20/80;
Moderate 5/25; else Low. CHIRPS is used only as the label, never as an input.
"""
from datetime import date, datetime, timedelta
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.api.services import imerg_early
from src.modeling.stage2.features import FEATURE_COLUMNS, FeatureError, build_features

ROOT = Path(__file__).resolve().parents[3]
RUNS = ROOT / "data/stage2/ifs_runs"
def latest_chirps() -> Path:
    """Newest merged label file written by src.scripts.prepare_chirps_labels."""
    files = sorted((ROOT / "data/stage2").glob("CHIRPS_Nairobi_zones_2016_*.csv"))
    if not files:
        raise FileNotFoundError("no merged CHIRPS label file in data/stage2 (run prepare_chirps_labels)")
    return files[-1]


ZONES = {z["id"]: z for z in json.loads((ROOT / "tests/fixtures/operational_sources/zones.json").read_text())["zones"]}


def chirps_labels(path: Path | None = None) -> pd.DataFrame:
    c = pd.read_csv(path or latest_chirps(), parse_dates=["date"]).sort_values(["zone_id", "date"])
    c["r7"] = c.groupby("zone_id")["precipitation"].transform(lambda s: s.rolling(7, min_periods=7).sum())
    c = c.dropna(subset=["r7"])
    p, r7 = c["precipitation"], c["r7"]
    c["label"] = np.select([(p >= 40) | (r7 >= 150), (p >= 20) | (r7 >= 80), (p >= 5) | (r7 >= 25)], [3, 2, 1], 0)
    return c.rename(columns={"date": "target_date", "precipitation": "chirps_target_mm", "r7": "chirps_7d_mm"})


def observed_days(zone: dict, issue: date, root: Path | None = None) -> tuple[list[float] | None, str | None]:
    i, j = imerg_early.cell_index(zone["latitude"], zone["longitude"])
    cid = imerg_early.cell_id(i, j)
    values, versions = [], set()
    for day in imerg_early.antecedent_days(issue):
        record = imerg_early.read_day(day, root)
        cell = (record or {}).get("cells", {}).get(cid)
        if not cell or not cell["complete"]:
            return None, None
        values.append(cell["precipitation_mm"])
        versions.add(record["version"])
    return values, "+".join(sorted(versions))


def build_table(runs: Path = RUNS, chirps: Path | None = None, imerg_root: Path | None = None) -> tuple[pd.DataFrame, dict]:
    rows, skipped = [], {}
    for path in sorted(runs.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        issue = datetime.fromisoformat(record["run_utc"]).date()
        for zone_id, item in zip(record["zones"], record["payload"], strict=True):
            observed, version = observed_days(ZONES[zone_id], issue, imerg_root)
            if observed is None:
                skipped["imerg_incomplete"] = skipped.get("imerg_incomplete", 0) + 1
                continue
            try:
                features = build_features(item["hourly"], issue, observed)
            except (FeatureError, KeyError) as exc:
                skipped[type(exc).__name__] = skipped.get(type(exc).__name__, 0) + 1
                continue
            rows.append(dict(issue_date=pd.Timestamp(issue), target_date=pd.Timestamp(issue + timedelta(days=1)),
                             zone_id=zone_id, imerg_version=version, **features))
    table = pd.DataFrame(rows)
    labels = chirps_labels(chirps)
    table = table.merge(labels[["target_date", "zone_id", "label", "chirps_target_mm", "chirps_7d_mm"]],
                        on=["target_date", "zone_id"], how="inner", validate="one_to_one")
    assert table[list(FEATURE_COLUMNS)].notna().all().all()
    return table.sort_values(["issue_date", "zone_id"]).reset_index(drop=True), skipped
