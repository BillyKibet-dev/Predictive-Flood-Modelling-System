"""Export CHIRPS daily rainfall for the eight Nairobi monitoring boxes, 1 Dec 2025 -> latest available.

Run in Google Colab (paste into one cell, or upload and `%run`). It extends
CHIRPS_Nairobi_zones_2016_2025.csv for Stage 2 labels, using the SAME boxes, reducer
and date format as that file.

Safety gates, in order (the script stops at the first failure):
  1. Reference check: recompute two days already in the existing CSV (30 Apr 2024,
     31 Dec 2025). The export runs only if they match to 1e-4 mm, proving the method is
     identical. If the default scale does not match, other plausible scales are tried and
     the matching one is used (and printed).
  2. Coverage: report the latest CHIRPS day Earth Engine currently holds (CHIRPS final
     data is published with a lag of roughly 3-6 weeks).
  3. Preflight: a 7-day sample must contain numeric rainfall for all 8 zones.

Output (Google Drive > Project Dataset):  CHIRPS_Nairobi_zones_2025-12-01_to_<latest>.csv
Columns: date, zone_id, precipitation   (same as the existing file)

December 2025 is deliberately re-exported as an overlap; the local merge script
(`python -m src.scripts.prepare_chirps_labels`) checks it against the existing file again.

Note: the reduction scale controls how the ~5.5 km CHIRPS grid is sampled over each box;
it does not create finer-resolution rainfall.
"""
import ee

ee.Authenticate()
ee.Initialize(project="flood-prediction-system-501809")

ZONES = {
    "mathare": [36.845, -1.275, 36.880, -1.245],
    "kibera": [36.770, -1.325, 36.810, -1.295],
    "westlands": [36.795, -1.275, 36.825, -1.250],
    "cbd": [36.810, -1.295, 36.835, -1.270],
    "kasarani": [36.870, -1.235, 36.920, -1.200],
    "embakasi": [36.875, -1.335, 36.920, -1.300],
    "dagoretti": [36.735, -1.310, 36.775, -1.280],
    "ruaraka": [36.860, -1.255, 36.900, -1.220],
}

# Values copied from the existing CHIRPS_Nairobi_zones_2016_2025.csv (mm/day).
REFERENCE = {
    "2024-04-30": {"mathare": 36.758086, "kibera": 57.923819, "westlands": 54.745372, "cbd": 54.200695,
                   "kasarani": 38.190454, "embakasi": 41.74598, "dagoretti": 60.448176, "ruaraka": 34.097556},
    "2025-12-31": {"mathare": 19.562873, "kibera": 18.084428, "westlands": 16.82105, "cbd": 17.050394,
                   "kasarani": 12.902253, "embakasi": 17.890507, "dagoretti": 17.298519, "ruaraka": 20.668358},
}
CANDIDATE_SCALES = [5566, 5000, 1000, 11132]   # 5566 is what the original export script used
TOLERANCE_MM = 1e-4
EXPORT_START = "2025-12-01"                    # one month overlap with the existing file

zones = ee.FeatureCollection([
    ee.Feature(ee.Geometry.Rectangle(bounds), {"zone_id": name}) for name, bounds in ZONES.items()
])
chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")


def per_day(scale):
    def reduce(image):
        date = image.date().format("YYYY-MM-dd")
        reduced = image.reduceRegions(collection=zones, reducer=ee.Reducer.mean(), scale=scale, tileScale=4)
        return reduced.map(lambda f: ee.Feature(None, {
            "date": date, "zone_id": f.get("zone_id"), "precipitation": f.get("mean")}))
    return reduce


def reference_matches(scale):
    worst = 0.0
    for day, expected in REFERENCE.items():
        next_day = ee.Date(day).advance(1, "day")
        rows = chirps.filterDate(day, next_day).map(per_day(scale)).flatten().getInfo()["features"]
        got = {r["properties"]["zone_id"]: r["properties"]["precipitation"] for r in rows}
        if set(got) != set(expected) or any(v is None for v in got.values()):
            return False, float("inf")
        worst = max(worst, max(abs(got[z] - expected[z]) for z in expected))
    return worst <= TOLERANCE_MM, worst


# ---- Gate 1: identical method --------------------------------------------------------
SCALE = None
for scale in CANDIDATE_SCALES:
    ok, worst = reference_matches(scale)
    print(f"scale={scale:>6} m: max difference from existing CSV = {worst:.6f} mm -> {'MATCH' if ok else 'no match'}")
    if ok:
        SCALE = scale
        break
if SCALE is None:
    raise RuntimeError("No reduction scale reproduces the existing CSV. Do not export: the new rows would not be "
                       "comparable to 2016-2025. Check the zone boxes against the script that made the original file.")

# ---- Gate 2: what is available ------------------------------------------------------
recent = chirps.filterDate(EXPORT_START, "2030-01-01")
count = recent.size().getInfo()
if count == 0:
    raise RuntimeError("Earth Engine has no CHIRPS daily images after 2025-12-01. Check the dataset catalogue "
                       "(https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY) "
                       "for a newer CHIRPS version before continuing.")
latest = ee.Date(recent.aggregate_max("system:time_start")).format("YYYY-MM-dd").getInfo()
export_end = ee.Date(latest).advance(1, "day")   # filterDate excludes its end
print(f"CHIRPS daily images from {EXPORT_START}: {count}; latest available day: {latest}")

# ---- Gate 3: preflight sample ---------------------------------------------------------
sample = chirps.filterDate(EXPORT_START, ee.Date(EXPORT_START).advance(7, "day")).map(per_day(SCALE)).flatten()
rows, numeric = sample.size().getInfo(), sample.filter(ee.Filter.notNull(["precipitation"])).size().getInfo()
print(f"Preflight: {numeric}/{rows} sample rows have numeric rainfall")
if rows != 7 * len(ZONES) or numeric != rows:
    raise RuntimeError("Preflight found missing zones or empty rainfall values; do not export.")

# ---- Export ---------------------------------------------------------------------------
name = f"CHIRPS_Nairobi_zones_{EXPORT_START}_to_{latest}"
task = ee.batch.Export.table.toDrive(
    collection=recent.filterDate(EXPORT_START, export_end).map(per_day(SCALE)).flatten(),
    description=name.replace("-", "_"),
    folder="Project Dataset",
    fileNamePrefix=name,
    fileFormat="CSV",
    selectors=["date", "zone_id", "precipitation"],
)
task.start()
print(f"\nExport submitted: {task.id}  (scale={SCALE} m, {EXPORT_START} .. {latest})")
print("Track it at https://code.earthengine.google.com/tasks ; when COMPLETED, download",
      f"Google Drive > Project Dataset > {name}.csv")
print("Then place it in the repository at data/stage2/ and run:  python -m src.scripts.prepare_chirps_labels")
