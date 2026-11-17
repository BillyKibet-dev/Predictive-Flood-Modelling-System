"""CHIRPS extension validation/merge, on synthetic files (the real v1 file is never written)."""
import pandas as pd
import pytest

from src.scripts import prepare_chirps_labels as prep

ZONES = sorted(prep.ZONES)


def frame(start, end, value=lambda day, zone: 1.0):
    days = pd.date_range(start, end, freq="D")
    return pd.DataFrame([dict(date=d.strftime("%Y-%m-%d"), zone_id=z, precipitation=value(d, z)) for d in days for z in ZONES])


def write(tmp_path, name, df):
    path = tmp_path / name
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def files(tmp_path):
    rain = lambda d, z: float(d.day) + ZONES.index(z) / 10
    original = write(tmp_path, "original.csv", frame("2025-11-01", "2025-12-31", rain))
    extension = write(tmp_path, "CHIRPS_Nairobi_zones_2025-12-01_to_2026-02-28.csv", frame("2025-12-01", "2026-02-28", rain))
    return tmp_path, original, extension, rain


def test_valid_extension_merges_after_matching_overlap(files):
    tmp, original, extension, _ = files
    assert prep.main(["--input", str(extension), "--original", str(original), "--output-dir", str(tmp)]) == 0
    merged = pd.read_csv(tmp / "CHIRPS_Nairobi_zones_2016_2026-02-28.csv")
    assert len(merged) == (30 + 31 + 31 + 28) * 8 and merged.duplicated(["date", "zone_id"]).sum() == 0
    assert (tmp / "CHIRPS_Nairobi_zones_2016_2026-02-28.manifest.json").exists()


def test_different_extraction_method_is_rejected(files):
    tmp, original, _, rain = files
    shifted = write(tmp, "ext.csv", frame("2025-12-01", "2026-01-31", lambda d, z: rain(d, z) * 1.05))
    assert prep.main(["--input", str(shifted), "--original", str(original), "--output-dir", str(tmp)]) == 1


@pytest.mark.parametrize("damage", [
    lambda df: df.drop(index=5),                                       # a zone missing on one date
    lambda df: pd.concat([df, df.iloc[[0]]]),                          # duplicate row
    lambda df: df.assign(precipitation=df.precipitation.where(df.index != 3)),   # empty rainfall
    lambda df: df.assign(precipitation=df.precipitation.where(df.index != 3, -1.0)),
    lambda df: df[df.date != "2026-01-15"],                            # missing day
    lambda df: df.rename(columns={"precipitation": "mean"}),           # wrong column
])
def test_damaged_exports_never_merge(files, damage):
    tmp, original, _, rain = files
    bad = write(tmp, "bad.csv", damage(frame("2025-12-01", "2026-01-31", rain)))
    assert prep.main(["--input", str(bad), "--original", str(original), "--output-dir", str(tmp)]) == 1


def test_export_without_overlap_is_rejected(files):
    tmp, original, _, rain = files
    no_overlap = write(tmp, "late.csv", frame("2026-01-01", "2026-01-31", rain))
    assert prep.main(["--input", str(no_overlap), "--original", str(original), "--output-dir", str(tmp)]) == 1
