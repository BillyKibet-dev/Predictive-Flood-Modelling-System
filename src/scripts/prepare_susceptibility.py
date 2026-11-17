"""Local flood susceptibility for each monitored place (offline; the API only reads the output).

Tomorrow's rainfall is nearly the same across neighbouring places (36 places share 7 forecast
cells), so the rainfall category alone cannot say which place floods first. This adds what
does differ locally, from pinned sources:

* terrain (Copernicus DEM GLO-30, ~30 m): height above the nearest mapped river or stream
  (a simple HAND, "height above nearest drainage") and how much lower the place sits than
  the ground within 250 m;
* OpenStreetMap rivers, streams and canals (one Overpass extract): distance to the nearest;
* the UNOSAT 1 May 2024 satellite water map (already in the catalogue): water within 250 m;
* ESA WorldCover 2021 built-up share (already in the enrichment): sealed ground;
* recorded observed flooding at the place (catalogue evidence).

Points are added with fixed, documented weights. The result ranks the monitored places
against each other; it is not a validated flood probability.

    python -m src.scripts.prepare_susceptibility
"""
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data/hotspots/gis_dependencies"))   # bundled rasterio/numpy (offline only)
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.transform import rowcol  # noqa: E402

from src.api.services.monitoring_area_service import load_catalog  # noqa: E402

# Two 1-degree tiles: 36-37 E (most of Nairobi) and 37-38 E (the far east, e.g. Gituamba).
DEM_TILES = {
    36: (ROOT / "data/hotspots/evidence/raw/sha256/e7/e7984d6826564293fff54b518250b9e3f8b0fd68b119d618ae6f66a515d145ed.bin",
         "e7984d6826564293fff54b518250b9e3f8b0fd68b119d618ae6f66a515d145ed"),
    # Not in git; re-download from https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_S02_00_E037_00_DEM/
    37: (ROOT / "data/susceptibility/source/Copernicus_DSM_COG_10_S02_00_E037_00_DEM.tif",
         "4d65f18cdbe9b3f74b8f4400abbd3072b1984ac375c3472c9da74039f948ef53"),
}
WATERWAYS = ROOT / "data/susceptibility/source/osm_waterways_nairobi_2026-11-15.json"
WATERWAYS_SHA256 = "1086ddfb48aeff90f0c7dc82938e7d5e015582b45d721057f455b7ecb6e6c8c7"
ENRICHMENT = ROOT / "src/api/data/monitoring_point_enrichment.json"
OUTPUT = ROOT / "src/api/data/monitoring_susceptibility.json"
RELIEF_RADIUS_M = 250
EARTH_M = 6371008.8

# Fixed weights, declared before looking at the result. Max 10 points.
WEIGHTS = [
    ("height_above_river", "Close in height to a river or stream", [(5, 3), (15, 2), (30, 1)]),
    ("relief", "Lower than the ground around it", [(-3, 2), (-1, 1)]),
    ("river_distance", "Within 100 m of a river or stream", [(100, 1)]),
    ("satellite_water", "Satellite saw water within 250 m on 1 May 2024", [(250, 2)]),
    ("built_up", "Mostly sealed ground (roofs, roads)", [(0.85, 1)]),
    ("observed", "Flooding recorded here before", [(1, 1)]),
]
CLASSES = [(6, "Higher"), (3, "Medium"), (0, "Lower")]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_xy(lon, lat, lon0, lat0):
    return (math.radians(lon - lon0) * EARTH_M * math.cos(math.radians(lat0)), math.radians(lat - lat0) * EARTH_M)


def nearest_waterway(lon, lat, ways):
    best = (float("inf"), None, None)
    for way in ways:
        pts = [local_xy(p["lon"], p["lat"], lon, lat) for p in way["geometry"]]
        for (x1, y1), (x2, y2), g1, g2 in zip(pts, pts[1:], way["geometry"], way["geometry"][1:]):
            dx, dy = x2 - x1, y2 - y1
            t = max(0.0, min(1.0, -(x1 * dx + y1 * dy) / (dx * dx + dy * dy or 1)))
            d = math.hypot(x1 + t * dx, y1 + t * dy)
            if d < best[0]:
                best = (d, way, (g1["lon"] + t * (g2["lon"] - g1["lon"]), g1["lat"] + t * (g2["lat"] - g1["lat"])))
    return best


def points_for(value, steps, lower_is_worse=True):
    if value is None:
        return 0
    for limit, pts in steps:
        if (value <= limit) if lower_is_worse else (value >= limit):
            return pts
    return 0


def main():
    if any(sha256(path) != digest for path, digest in DEM_TILES.values()) or sha256(WATERWAYS) != WATERWAYS_SHA256:
        raise SystemExit("A pinned source changed; nothing written.")
    ways = [w for w in json.loads(WATERWAYS.read_bytes())["elements"] if w.get("geometry")]
    catalog = load_catalog()
    enrichment = {r["area_id"]: r for r in json.loads(ENRICHMENT.read_text(encoding="utf-8"))["rows"]}
    rows = []
    tiles = {}
    for key, (path, _) in DEM_TILES.items():
        with rasterio.open(path) as dem:
            tiles[key] = (dem.read(1).astype("float64"), dem.transform)
    if True:
        def tile(lon):
            return tiles[math.floor(lon)]

        def elevation(lon, lat, size=1):
            band, transform = tile(lon)
            r, c = rowcol(transform, lon, lat)
            return band[r - size:r + size + 1, c - size:c + size + 1]

        pixel_m = abs(tiles[36][1].a) * math.pi / 180 * EARTH_M
        radius_px = round(RELIEF_RADIUS_M / pixel_m)
        yy, xx = np.mgrid[-radius_px:radius_px + 1, -radius_px:radius_px + 1]
        ring = (np.hypot(yy, xx) <= radius_px) & (np.hypot(yy, xx) > 1.5)

        for site in catalog["sites"]:
            if not site.get("geometry"):
                continue
            lon, lat = site["geometry"]["coordinates"]
            here = float(np.median(elevation(lon, lat)))            # 3x3 median: less building noise
            block = elevation(lon, lat, size=radius_px)
            if block.shape != ring.shape:
                raise SystemExit(f"{site['id']}: {lon},{lat} -> {r},{c} block {block.shape}")
            around = block[ring]
            relief = here - float(np.mean(around))
            distance, way, foot = nearest_waterway(lon, lat, ways)
            channel = float(np.min(elevation(*foot)))               # lowest pixel next to the channel
            height_above = here - channel
            water = site.get("nearby_water_reference") or {}
            covered = (water.get("analysis_coverage_percent") or 0) > 0
            built = ((enrichment.get(site["id"]) or {}).get("landcover") or {}).get("built_up_fraction")
            observed = site.get("evidence_category") == "OBSERVED_FLOOD_OR_IMPACT"
            values = dict(height_above_river=height_above, relief=relief, river_distance=distance,
                          satellite_water=water.get("distance_m") if covered else None,
                          built_up=built, observed=1 if observed else None)
            factors, score = [], 0
            for key, text, steps in WEIGHTS:
                pts = points_for(values[key], steps, lower_is_worse=key not in ("built_up", "observed"))
                score += pts
                factors.append(dict(key=key, label=text, points=pts, max_points=max(p for _, p in steps)))
            level = next(name for minimum, name in CLASSES if score >= minimum)
            rows.append(dict(
                area_id=site["id"], score=score, max_score=10, level=level,
                height_above_river_m=round(height_above, 1), relief_m=round(relief, 1),
                river_distance_m=round(distance), river_name=(way["tags"].get("name") or f"unnamed {way['tags']['waterway']}"),
                river_kind=way["tags"]["waterway"], elevation_m=round(here, 1),
                satellite_water_m=None if values["satellite_water"] is None else round(values["satellite_water"]),
                satellite_covered=covered, built_up_fraction=None if built is None else round(built, 2),
                observed_flooding=observed, factors=factors))
    document = dict(
        contract_version="monitoring-susceptibility-v1",
        method=("Points from fixed weights: height above the nearest mapped river or stream (<=5 m: 3, <=15 m: 2, "
                "<=30 m: 1), lower than the ground within 250 m (<=-3 m: 2, <=-1 m: 1), within 100 m of a river (1), "
                "satellite water within 250 m on 1 May 2024 (2), built-up share >=0.85 (1), recorded flooding (1). "
                "Higher >=6, Medium 3-5, Lower <=2."),
        sources=dict(dem=dict(name="Copernicus DEM GLO-30 (surface model, ~30 m), tiles S02 E036 and S02 E037",
                              sha256=[digest for _, digest in DEM_TILES.values()],
                              licence="Copernicus DEM licence; (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH 2014-2018"),
                     waterways=dict(name="OpenStreetMap waterways (river, stream, canal), Overpass extract 15 Nov 2026",
                                    sha256=WATERWAYS_SHA256, licence="ODbL; (c) OpenStreetMap contributors"),
                     satellite_water="UNOSAT 1 May 2024 Nairobi water map (catalogue)",
                     built_up="ESA WorldCover 2021 (enrichment)"),
        catalog_sha256=catalog["inventory_sha256"] if "inventory_sha256" in catalog else None,
        limitations=["A ranking of the monitored places against each other, not a validated flood probability.",
                     "The terrain model is a surface model (includes buildings) at ~30 m; it cannot see drains, culvert "
                     "capacity or blockages.",
                     "OpenStreetMap may miss small streams and drains.",
                     "The 2024 satellite scene does not cover western Nairobi; no water there means not observed, not dry."],
        rows=rows)
    OUTPUT.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(dict(output=str(OUTPUT.relative_to(ROOT)), sha256=sha256(OUTPUT),
                          levels={k: sum(r["level"] == k for r in rows) for k in ("Higher", "Medium", "Lower")})))


if __name__ == "__main__":
    main()
