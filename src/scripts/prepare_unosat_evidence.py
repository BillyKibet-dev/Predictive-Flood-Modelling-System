"""Offline, explicit preparation of authentic UNOSAT source members. No DDL/inference.

Optional preparation dependencies: pyshp==3.1.7 and shapely==2.2.0.
Runtime API uses only standard JSON and existing PostgreSQL/PostGIS.
"""
import hashlib
import io
import json
from pathlib import Path

from sqlalchemy import text

KINDS = {'flood': 'FloodExtent', 'coverage': 'AnalysisExtent', 'cloud': 'CloudObstruction'}
PREFIX = 'PL_20240501_{}_Nairobi_Kiambu'


def decode_shape(shape):
    """Shapefile CW shells/CCW holes, indexed implementation of pyshp grouping.

    Original coordinates are retained, including invalid topology for explicit review.
    No orphan hole is promoted to a detected area.
    """
    import shapefile
    from shapely.geometry import Polygon, MultiPolygon
    from shapely.strtree import STRtree
    from shapely import prepare as prepare_geometries
    parts = list(shape.parts) + [len(shape.points)]
    rings = [shape.points[a:b] for a, b in zip(parts, parts[1:])]
    if not rings or any(len(r) < 4 or r[0] != r[-1] for r in rings):
        raise ValueError('Empty or unclosed native polygon')
    shells = [r for r in rings if shapefile.is_cw(r)]
    holes = [r for r in rings if not shapefile.is_cw(r)]
    if not shells: raise ValueError('No native exterior rings')
    polygons = [Polygon(r) for r in shells]
    prepare_geometries(polygons)
    tree = STRtree(polygons)
    groups = [[] for _ in shells]
    for hole in holes:
        box = shapefile.ring_bbox(hole)
        candidates = [int(i) for i in tree.query(Polygon(hole)) if shapefile.bbox_contains(polygons[int(i)].bounds, box)]
        if len(candidates) > 1:
            point = Polygon(hole).representative_point()
            candidates = [i for i in candidates if polygons[i].contains(point)]
        if not candidates: raise ValueError('Orphan hole; scientific review required')
        parent = min(candidates, key=lambda i: polygons[i].area)
        groups[parent].append(hole)
    return MultiPolygon([Polygon(shell, groups[i]) for i, shell in enumerate(shells)])


def read_native(read_member, kind):
    import shapefile
    stem = PREFIX.format(KINDS[kind])
    parts = {suffix: read_member(stem + suffix) for suffix in ('.shp', '.shx', '.dbf', '.prj', '.cpg', '.shp.xml')}
    prj = parts['.prj'].decode()
    if not prj.startswith('GEOGCS["GCS_WGS_1984"') or 'UNIT["Degree"' not in prj:
        raise ValueError('Unapproved native CRS')
    reader = shapefile.Reader(shp=io.BytesIO(parts['.shp']), shx=io.BytesIO(parts['.shx']),
                              dbf=io.BytesIO(parts['.dbf']), encoding=parts['.cpg'].decode().strip())
    if reader.shapeTypeName != 'POLYGON': raise ValueError('Expected 2D polygon source')
    rows = []
    for sr in reader.iterShapeRecords():
        attrs = sr.record.as_dict()
        if str(attrs.get('SensorDate', attrs.get('Sensor_Dat'))) != '2024-05-01' or attrs.get('EventCod', attrs.get('EventCode')) != 'FL20240426KEN':
            raise ValueError('Unexpected source event/date')
        rows.append({'wkb': decode_shape(sr.shape).wkb_hex, 'attributes': attrs})
    if not rows: raise ValueError('Empty source layer')
    return rows, dict(native_crs=prj, native_horizontal_epsg=4326, vertical_coordinates_present=False,
                      members={stem + s: {'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)} for s, b in parts.items()})


def prepare(connection, read_member, output):
    """Build a reproducible bundle. All spatial operations run in read-only SQL."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    layers, review, native = {}, {}, {}
    for kind in KINDS:
        rows, native[kind] = read_native(read_member, kind)
        checks = []
        fixed = []
        for row in rows:
            result = dict(connection.execute(text('''WITH g AS MATERIALIZED (
              SELECT ST_SetSRID(ST_GeomFromWKB(decode(:wkb,'hex')),4326) AS v),
              f AS MATERIALIZED (SELECT v, ST_Multi(ST_CollectionExtract(ST_MakeValid(v,'method=structure keepcollapsed=false'),3)) AS valid FROM g)
              SELECT ST_IsValid(v) AS original_valid, ST_IsValidReason(v) AS original_reason,
              ST_NPoints(v) AS original_points, ST_Area(ST_Transform(v,32737)) AS original_area_m2,
              ST_IsValid(valid) AS repaired_valid, ST_Area(ST_Transform(valid,32737)) AS repaired_area_m2,
              ST_NPoints(valid) AS repaired_points, encode(ST_AsEWKB(valid),'hex') AS repaired_wkb,
              ST_IsEmpty(valid) AS repaired_empty FROM f'''), {'wkb': row['wkb']}).mappings().one())
            if not result['repaired_valid'] or result['repaired_empty']: raise ValueError('Unusable repaired geometry')
            fixed.append(result.pop('repaired_wkb'))
            checks.append(result)
        # Dissolve overlaps within each authentic layer; no fabricated extent.
        full = fixed[0] if len(fixed) == 1 else connection.execute(text('''SELECT encode(ST_AsEWKB(ST_UnaryUnion(ST_Collect(
          ST_GeomFromEWKB(decode(value,'hex'))))),'hex') FROM jsonb_array_elements_text(CAST(:items AS jsonb))'''),
          {'items': json.dumps(fixed)}).scalar()
        native[kind]['repaired_union_wkb'] = full  # Local full-resolution analysis only.
        # Preserve polygon topology in metric UTM37S, then return WGS84 RFC7946.
        display = dict(connection.execute(text('''WITH g AS MATERIALIZED (SELECT ST_GeomFromEWKB(decode(:g,'hex')) AS v),
          s AS MATERIALIZED (SELECT v,ST_Transform(ST_SimplifyPreserveTopology(ST_Transform(v,32737),1.0),4326) AS simple FROM g)
          SELECT ST_AsGeoJSON(ST_ForcePolygonCCW(simple),9,0) AS geometry,ST_IsValid(simple) AS valid,
          ST_Area(ST_Transform(v,32737)) AS full_area_m2, ST_Area(ST_Transform(simple,32737)) AS display_area_m2,
          ST_NPoints(v) AS full_points, ST_NPoints(simple) AS display_points
          FROM s'''), {'g': full}).mappings().one())
        if not display['valid'] or abs(display['display_area_m2'] / display['full_area_m2'] - 1) > .01:
            raise ValueError('Display topology/area drift requires review')
        geometry = json.loads(display.pop('geometry'))
        document = {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'id': 'unosat-20240501-' + kind,
                     'properties': {'layer_kind': kind, 'acquired_at': '2024-05-01T08:06:00Z', 'provider': 'UNITAR-UNOSAT',
                                    'field_validation': 'Not yet field validated'}, 'geometry': geometry}]}
        raw = (json.dumps(document, separators=(',', ':'), allow_nan=False) + '\n').encode()
        if len(raw) > 8_000_000: raise ValueError('Display layer exceeds response cap')
        path = output / (kind + '.geojson')
        if path.exists() and path.read_bytes() != raw: raise ValueError('Output differs; use a new version directory')
        path.write_bytes(raw)
        layers[kind] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        review[kind] = {'native_features': checks, 'display': display, 'simplification_tolerance_m': 1.0}
    return dict(layers=layers, geometry_review=review, native=native)


def compare_geography(connection, native):
    """Full-resolution point assessments and distinct administrative context."""
    params = {k: native[k]['repaired_union_wkb'] for k in KINDS}
    source = '''WITH s AS MATERIALIZED (SELECT ST_GeomFromEWKB(decode(:flood,'hex')) AS flood,
        ST_GeomFromEWKB(decode(:coverage,'hex')) AS coverage,ST_GeomFromEWKB(decode(:cloud,'hex')) AS cloud)'''
    points = [dict(r) for r in connection.execute(text(source + '''
        SELECT z.id AS zone_id,z.name,z.latitude,z.longitude,
        CASE WHEN NOT ST_Covers(s.coverage,p.g) THEN 'OUTSIDE_ANALYSIS'
             WHEN ST_Covers(s.cloud,p.g) THEN 'CLOUD_OBSCURED'
             WHEN ST_Covers(s.flood,p.g) THEN 'DETECTION_INTERSECTION'
             ELSE 'NO_DETECTION_REPORTED' END AS observation_state,
        NULL::boolean AS confirmed_flood_free
        FROM zones z CROSS JOIN s CROSS JOIN LATERAL
          (SELECT ST_SetSRID(ST_MakePoint(z.longitude,z.latitude),4326) AS g) p ORDER BY z.id'''), params).mappings()]
    context = [dict(r) for r in connection.execute(text(source + ''', m AS MATERIALIZED (
        SELECT ST_Transform(flood,32737) AS f,ST_Transform(coverage,32737) AS a,ST_Transform(cloud,32737) AS c FROM s),
        u AS MATERIALIZED (SELECT *,ST_Difference(a,c) AS usable FROM m)
        SELECT b.id AS boundary_id,b.name,
          (SELECT json_agg(z.id ORDER BY z.id) FROM zones z WHERE
            ST_Covers(b.geometry,ST_SetSRID(ST_MakePoint(z.longitude,z.latitude),4326))) AS monitoring_zone_ids,
          100*ST_Area(ST_Intersection(g.v,usable))/ST_Area(g.v) AS usable_coverage_percent,
          100*ST_Area(ST_Intersection(g.v,ST_Intersection(a,c)))/ST_Area(g.v) AS cloud_percent,
          100*(1-ST_Area(ST_Intersection(g.v,a))/ST_Area(g.v)) AS outside_analysis_percent,
          ST_Area(ST_Intersection(g.v,ST_Intersection(f,usable)))/1e6 AS detected_water_usable_km2
        FROM administrative_boundaries b CROSS JOIN u CROSS JOIN LATERAL
          (SELECT ST_Transform(b.geometry,32737) AS v) g WHERE b.admin_level=2 AND EXISTS
          (SELECT 1 FROM zones z WHERE ST_Covers(b.geometry,ST_SetSRID(ST_MakePoint(z.longitude,z.latitude),4326))) ORDER BY b.id'''), params).mappings()]
    # Include source consistency diagnostics without interpreting missing coverage as negative evidence.
    checks = dict(connection.execute(text(source + ''' SELECT
        ST_Area(ST_Transform(ST_Difference(flood,coverage),32737)) AS detected_water_outside_analysis_m2,
        ST_Area(ST_Transform(ST_Intersection(flood,cloud),32737)) AS detected_water_overlapping_cloud_m2,
        ST_Area(ST_Transform(coverage,32737)) AS analysis_area_m2,
        ST_Area(ST_Transform(ST_Difference(coverage,cloud),32737)) AS usable_analysis_area_m2 FROM s'''), params).mappings().one())
    for area in context:
        for key in ('usable_coverage_percent', 'cloud_percent', 'outside_analysis_percent'):
            if not -1e-8 <= area[key] <= 100 + 1e-8: raise ValueError('Invalid coverage fraction')
            area[key] = max(0., min(100., area[key]))  # Only floating-point boundary roundoff.
    return points, context, checks


def main():
    import argparse, sys, zipfile
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reader-path', type=Path)
    parser.add_argument('--manifest-output', type=Path, help='Write regenerated safe metadata for review; does not update the trusted runtime manifest automatically')
    args = parser.parse_args()
    if args.reader_path: sys.path.insert(0, str(args.reader_path.resolve()))
    from src.api.database import engine
    from src.api.services.historical_flood_service import MANIFEST_PATH, geometry_fingerprint
    template = json.loads(MANIFEST_PATH.read_bytes())
    with zipfile.ZipFile(args.archive) as archive, engine.connect() as connection:
        connection.execute(text('SET TRANSACTION READ ONLY'))
        def member(name):
            matches = [n for n in archive.namelist() if n.rsplit('/',1)[-1] == name]
            if len(matches) != 1: raise ValueError('Ambiguous or missing native member')
            raw = archive.read(matches[0])
            expected = template['source_members'].get(name)
            if not expected or len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
                raise ValueError('Source differs from the reviewed native member contract')
            return raw
        result = prepare(connection, member, args.output)
        if args.manifest_output:
            points, context, consistency = compare_geography(connection, result['native'])
            template.update(monitoring_points=points, administrative_context=context,
                            geography_fingerprint=geometry_fingerprint(connection))
            template['layers'] = result['layers']
            template['geometry_processing'].update(review=result['geometry_review'], source_consistency=consistency)
            if args.manifest_output.resolve() == MANIFEST_PATH.resolve():
                raise ValueError('Write a separate review manifest; do not overwrite the runtime contract automatically')
            with args.manifest_output.open('x', encoding='utf-8') as handle:
                json.dump(template, handle, indent=2); handle.write('\n')
    (args.output / 'preparation-review.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__': main()
