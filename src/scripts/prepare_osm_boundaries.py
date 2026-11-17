"""Build the packaged Nairobi county and 17 constituency (sub-county) outlines from OpenStreetMap.

    python -m src.scripts.prepare_osm_boundaries <nominatim-lookup.geojson> [--fetch]

The map basemap is OpenStreetMap, so OSM's own boundaries line up with it. The previous
geoBoundaries 2020 layers sat 250-800 m north of the basemap, the county outline came from a
different dataset than the sub-counties (up to 3 km apart), and Kibera's villages fell in
Langata instead of Kibra.

Checks before writing: every polygon is valid; no two constituencies overlap; there are no
gaps; the constituencies together equal the OSM county outline. Shared edges are simplified
together (coverage simplification), so neighbours keep identical borders.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/boundaries"
COUNTY_RELATION = 3492709
# OSM boundary=political, political_division=constituency relations inside Nairobi County.
CONSTITUENCIES = {
    16132840: "Dagoretti North", 16132839: "Dagoretti South", 16132828: "Embakasi Central",
    16132826: "Embakasi East", 16132832: "Embakasi North", 16132825: "Embakasi South",
    16132827: "Embakasi West", 16132835: "Kamukunji", 16132829: "Kasarani", 16132838: "Kibra",
    16132837: "Langata", 16132834: "Makadara", 16132833: "Mathare", 16132842: "Roysambu",
    16132830: "Ruaraka", 16132836: "Starehe", 16132841: "Westlands",
}
LOOKUP_URL = "https://nominatim.openstreetmap.org/lookup"
TOLERANCE_DEG = 0.00003            # about 3 m; shared borders are simplified once, together
LICENSE = "Open Database License (ODbL) 1.0; (c) OpenStreetMap contributors"
SOURCE = "OpenStreetMap contributors (constituency relations), via Nominatim"
KM2_PER_DEG2 = 111.32 ** 2 * math.cos(math.radians(1.28))


def fetch(path: Path) -> None:
    import requests
    ids = ",".join(f"R{i}" for i in [*CONSTITUENCIES, COUNTY_RELATION])
    response = requests.get(LOOKUP_URL, params=dict(osm_ids=ids, format="geojson", polygon_geojson=1), timeout=60,
                            headers={"User-Agent": "NairobiFloodWatch-boundaries/1.0"})
    response.raise_for_status()
    path.write_bytes(response.content)


def slug(name: str) -> str:
    return "nairobi-subcounty-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def rounded(geometry: dict) -> dict:
    def walk(value):
        return [walk(v) for v in value] if isinstance(value[0], (list, tuple)) else [round(value[0], 6), round(value[1], 6)]
    return dict(type=geometry["type"], coordinates=walk(geometry["coordinates"]))


def check_coverage(parts: dict, county, label: str) -> None:
    from itertools import combinations
    from shapely.ops import unary_union
    for name, geometry in parts.items():
        if not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"{label}: invalid geometry for {name}")
    overlap = sum(a.intersection(b).area for (_, a), (_, b) in combinations(parts.items(), 2)) * KM2_PER_DEG2 * 1e6
    union = unary_union(list(parts.values()))
    gaps = county.difference(union).area * KM2_PER_DEG2 * 1e6
    outside = union.difference(county).area * KM2_PER_DEG2 * 1e6
    if overlap > 1 or gaps > 1 or outside > 1:
        raise ValueError(f"{label}: overlap {overlap:.1f} m2, gaps {gaps:.1f} m2, outside county {outside:.1f} m2")


def build(path: Path) -> dict:
    sys.path.insert(0, str(ROOT / "data/hotspots/gis_dependencies"))
    import shapely
    from shapely.geometry import mapping, shape
    raw = path.read_bytes()
    features = {f["properties"]["osm_id"]: f for f in json.loads(raw)["features"]}
    if set(features) != {*CONSTITUENCIES, COUNTY_RELATION}:
        raise ValueError("Lookup must contain exactly the 17 constituencies and the county relation")
    county = shape(features[COUNTY_RELATION]["geometry"])
    parts = {name: shape(features[i]["geometry"]) for i, name in CONSTITUENCIES.items()}
    check_coverage(parts, county, "source")
    names = list(parts)
    simplified = dict(zip(names, shapely.coverage_simplify(shapely.GeometryCollection([parts[n] for n in names]).geoms,
                                                           TOLERANCE_DEG, simplify_boundary=True)))
    # Re-read through GeoJSON rounding (6 decimals, about 0.1 m) exactly as served, then re-check.
    served = {n: shape(rounded(mapping(g))) for n, g in simplified.items()}
    county_served = shapely.union_all(list(served.values()))
    check_coverage(served, county_served, "served")
    deviation = max(parts[n].hausdorff_distance(served[n]) for n in names) * 111_000
    if deviation > 10:
        raise ValueError(f"Simplification moved a border by {deviation:.1f} m")
    retrieved = datetime.now(timezone.utc).date().isoformat()
    raw_sha = hashlib.sha256(raw).hexdigest()

    def feature(identifier, name, level, geometry, osm_id):
        return {"type": "Feature", "id": identifier, "geometry": rounded(mapping(geometry)), "properties": {
            "name": name, "admin_level": level, "country_code": "KEN", "source": SOURCE,
            "source_url": f"https://www.openstreetmap.org/relation/{osm_id}", "source_license": LICENSE,
            "source_year": retrieved[:4], "source_feature_id": f"osm-relation-{osm_id}"}}

    subcounties = {"type": "FeatureCollection", "features": [
        feature(slug(name), name, 2, served[name], osm_id) for osm_id, name in sorted(CONSTITUENCIES.items(), key=lambda x: x[1])]}
    county_doc = {"type": "FeatureCollection", "features": [
        feature("nairobi-county", "Nairobi County", 1, county_served, COUNTY_RELATION)]}
    stats = dict(vertices=sum(len(shapely.get_coordinates(g)) for g in served.values()),
                 max_border_shift_m=round(deviation, 2),
                 county_vs_osm_county_max_m=round(county.hausdorff_distance(county_served) * 111_000, 2))
    meta = dict(provider="OpenStreetMap", license=LICENSE, retrieved_on=retrieved, lookup_url=LOOKUP_URL,
                lookup_sha256=raw_sha, county_relation=COUNTY_RELATION,
                constituency_relations={str(k): v for k, v in CONSTITUENCIES.items()},
                processing=("17 OSM constituency relations (boundary=political, political_division=constituency). "
                            f"Checked valid, non-overlapping, gap-free and equal to the OSM county relation; "
                            f"coverage-simplified together at {TOLERANCE_DEG} degrees and rounded to 6 decimals. "
                            "The county outline is the union of the constituencies, so the two layers share every border."),
                limitations=("OSM boundaries are community-mapped, not an official survey. Constituencies are the "
                             "IEBC electoral units used as Nairobi's 17 sub-counties."),
                **stats)
    return dict(subcounties=subcounties, county=county_doc, meta=meta)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lookup", type=Path, help="Saved Nominatim lookup GeoJSON (written first with --fetch)")
    parser.add_argument("--fetch", action="store_true", help="Request the lookup once from Nominatim")
    args = parser.parse_args(argv)
    if args.fetch:
        fetch(args.lookup)
    result = build(args.lookup)
    for name, doc in (("nairobi_subcounties", result["subcounties"]), ("nairobi_county", result["county"])):
        body = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        (OUT / f"{name}.geojson").write_bytes(body)
        meta = dict(result["meta"], geojson_sha256=hashlib.sha256(body).hexdigest())
        (OUT / f"{name}.source.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result["meta"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
