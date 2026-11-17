"""Validate a CHIRPS extension export and merge it with the 2016-2025 file for Stage 2 labels.

    python -m src.scripts.prepare_chirps_labels                       # newest export in data/stage2/
    python -m src.scripts.prepare_chirps_labels --input path/to/export.csv

Checks: exact columns; the eight zones on every date; no duplicates or gaps; finite,
non-negative rainfall; and every overlapping day (December 2025) equal to the existing
file within 1e-4 mm, proving the same extraction method. Writes
data/stage2/CHIRPS_Nairobi_zones_2016_<last-day>.csv plus a JSON manifest with SHA-256
hashes. The original v1 file is read only and never modified.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "data/model_v1/CHIRPS_Nairobi_zones_2016_2025.csv"
STAGE2 = ROOT / "data/stage2"
ZONES = {"cbd", "dagoretti", "embakasi", "kasarani", "kibera", "mathare", "ruaraka", "westlands"}
COLUMNS = ["date", "zone_id", "precipitation"]
TOLERANCE_MM = 1e-4


class ChirpsError(ValueError):
    pass


def load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if list(frame.columns) != COLUMNS:
        raise ChirpsError(f"{path.name}: columns {list(frame.columns)} != {COLUMNS}")
    frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="raise")
    frame["precipitation"] = pd.to_numeric(frame["precipitation"], errors="coerce")
    if frame["precipitation"].isna().any() or not np.isfinite(frame["precipitation"]).all():
        raise ChirpsError(f"{path.name}: missing or non-numeric rainfall in {int(frame['precipitation'].isna().sum())} rows")
    if (frame["precipitation"] < 0).any():
        raise ChirpsError(f"{path.name}: negative rainfall")
    if set(frame["zone_id"]) != ZONES:
        raise ChirpsError(f"{path.name}: zones {sorted(set(frame['zone_id']))} are not the eight monitoring zones")
    if frame.duplicated(["date", "zone_id"]).any():
        raise ChirpsError(f"{path.name}: duplicate date/zone rows")
    per_date = frame.groupby("date")["zone_id"].nunique()
    if (per_date != len(ZONES)).any():
        raise ChirpsError(f"{path.name}: {int((per_date != len(ZONES)).sum())} dates lack all eight zones")
    expected = pd.date_range(frame["date"].min(), frame["date"].max(), freq="D")
    missing = expected.difference(per_date.index)
    if len(missing):
        raise ChirpsError(f"{path.name}: {len(missing)} missing dates, first {missing[0].date()}")
    return frame.sort_values(["date", "zone_id"]).reset_index(drop=True)


def merge(original: pd.DataFrame, extension: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    overlap = original.merge(extension, on=["date", "zone_id"], suffixes=("_original", "_new"))
    if overlap.empty:
        raise ChirpsError("no overlapping days: re-export starting 2025-12-01 so the method can be verified")
    worst = float((overlap["precipitation_original"] - overlap["precipitation_new"]).abs().max())
    if worst > TOLERANCE_MM:
        raise ChirpsError(f"overlap differs from the existing file by up to {worst:.4f} mm: different extraction method")
    new_rows = extension[extension["date"] > original["date"].max()]
    if new_rows.empty:
        raise ChirpsError("the export adds no days after the existing file")
    if new_rows["date"].min() != original["date"].max() + pd.Timedelta(days=1):
        raise ChirpsError("gap between the existing file and the new rows")
    combined = pd.concat([original, new_rows], ignore_index=True).sort_values(["date", "zone_id"])
    return combined, dict(overlap_rows=len(overlap), overlap_max_abs_diff_mm=worst, new_rows=len(new_rows),
                          new_first_day=str(new_rows["date"].min().date()), new_last_day=str(new_rows["date"].max().date()))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, help="extension CSV (default: newest CHIRPS_Nairobi_zones_2025-12-01_to_*.csv in data/stage2/)")
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--output-dir", type=Path, default=STAGE2)
    args = parser.parse_args(argv)
    source = args.input
    if source is None:
        candidates = sorted(args.output_dir.glob("CHIRPS_Nairobi_zones_2025-12-01_to_*.csv"))
        if not candidates:
            print(f"No export found in {args.output_dir}. Download it from Google Drive > Project Dataset first.")
            return 2
        source = candidates[-1]
    try:
        combined, summary = merge(load(args.original), load(source))
    except ChirpsError as exc:
        print(f"REJECTED: {exc}")
        return 1
    last = combined["date"].max().date()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"CHIRPS_Nairobi_zones_2016_{last}.csv"
    out = combined.assign(date=combined["date"].dt.strftime("%Y-%m-%d"))
    out.to_csv(output, index=False)
    manifest = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), output=output.name, output_sha256=sha256(output),
                    rows=len(combined), first_day=str(combined["date"].min().date()), last_day=str(last),
                    original=args.original.name, original_sha256=sha256(args.original),
                    extension=source.name, extension_sha256=sha256(source), **summary)
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
