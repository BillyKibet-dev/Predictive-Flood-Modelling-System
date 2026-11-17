"""Read-only, pinned historical satellite evidence. No inference or acquisition."""
import hashlib
import json
import math
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / 'src/api/data/unosat_20240501.json'
DEFAULT_ROOT = ROOT / 'data/historical_unosat/20240501'
DATASET_ID = 'unosat-20240501-nairobi-kiambu'
KINDS = ('flood', 'coverage', 'cloud')


class HistoricalEvidenceUnavailable(ValueError):
    pass


def geometry_fingerprint(connection):
    """Bind summaries to actual points and versioned administrative geometry."""
    points = [dict(r) for r in connection.execute(text('SELECT id,latitude,longitude FROM zones ORDER BY id')).mappings()]
    areas = [dict(r) for r in connection.execute(text('''SELECT id,md5(ST_AsEWKB(geometry)) AS geometry_md5
        FROM administrative_boundaries ORDER BY id''')).mappings()]
    return {'points': points, 'administrative_geometry': areas}


def validate_collection(document, kind):
    if document.get('type') != 'FeatureCollection' or document.get('crs') or not document.get('features') or len(document['features']) > 4:
        raise HistoricalEvidenceUnavailable('Invalid historical feature collection')
    vertices = 0
    for feature in document['features']:
        geometry = feature.get('geometry')
        if (feature.get('type') != 'Feature' or feature.get('crs') or not isinstance(geometry, dict)
                or geometry.get('crs') or geometry.get('type') not in ('Polygon', 'MultiPolygon')
                or feature.get('properties', {}).get('layer_kind') != kind
                or feature['properties'].get('acquired_at') != '2024-05-01T08:06:00Z'):
            raise HistoricalEvidenceUnavailable('Invalid historical layer identity')
        polygons = [geometry.get('coordinates')] if geometry['type'] == 'Polygon' else geometry.get('coordinates')
        if not isinstance(polygons, list) or not polygons: raise HistoricalEvidenceUnavailable('Empty geometry')
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon: raise HistoricalEvidenceUnavailable('Empty polygon')
            for ring in polygon:
                if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                    raise HistoricalEvidenceUnavailable('Invalid ring')
                vertices += len(ring)
                for pos in ring:
                    if (not isinstance(pos, list) or len(pos) != 2 or
                        any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) for v in pos)
                        or not 36.5 <= pos[0] <= 37.3 or not -1.6 <= pos[1] <= -.9):
                        raise HistoricalEvidenceUnavailable('Geometry outside reviewed Nairobi neighbourhood')
    if vertices > 300000: raise HistoricalEvidenceUnavailable('Historical geometry response too large')
    return document


class HistoricalFloodService:
    def __init__(self, root=DEFAULT_ROOT, manifest_path=MANIFEST_PATH):
        self.root, self.manifest_path = Path(root), Path(manifest_path)

    def read(self, db):
        # Authentication may already have queried its session. Use a separate
        # read-only connection rather than changing an existing transaction.
        with db.get_bind().connect() as connection:
            connection.execute(text('SET TRANSACTION READ ONLY'))
            return self._read(connection)

    def _read(self, connection):
        manifest = json.loads(self.manifest_path.read_bytes())
        if manifest['dataset_id'] != DATASET_ID or manifest['information_type'] != 'historical_satellite_observation':
            raise HistoricalEvidenceUnavailable('Unsupported historical dataset')
        if geometry_fingerprint(connection) != manifest['geography_fingerprint']:
            raise HistoricalEvidenceUnavailable('Geographic catalogue differs from reviewed source comparison')
        layers = {}
        for kind in KINDS:
            path = self.root / (kind + '.geojson')
            if not path.resolve().is_relative_to(self.root.resolve()) or path.stat().st_size > 8_000_000:
                raise HistoricalEvidenceUnavailable('Unusable historical layer file')
            raw = path.read_bytes()
            reference = manifest['layers'][kind]
            if len(raw) != reference['bytes'] or hashlib.sha256(raw).hexdigest() != reference['sha256']:
                raise HistoricalEvidenceUnavailable('Historical source checksum mismatch')
            document = validate_collection(json.loads(raw), kind)
            for f in document['features']:
                valid = connection.execute(text('SELECT ST_IsValid(ST_SetSRID(ST_GeomFromGeoJSON(:g),4326))'),
                                           {'g': json.dumps(f['geometry'])}).scalar()
                if not valid: raise HistoricalEvidenceUnavailable('Historical geometry is invalid')
            layers[kind] = document
        return manifest, layers

    def dataset(self, db):
        manifest, _ = self.read(db)
        # Explicit safe metadata only. Never return local paths or complete DBF records.
        return {k: manifest[k] for k in ('dataset_id', 'information_type', 'title', 'acquired_at', 'published_at',
            'product_id', 'source_url', 'download_url', 'provider', 'sensor', 'field_validation', 'confidence',
            'licence', 'licence_url', 'limitations', 'layers', 'monitoring_points', 'administrative_context',
            'archive_revision_published_at', 'source_members', 'geometry_processing')}

    def layer(self, db, kind):
        _, layers = self.read(db)
        return {**layers[kind], 'dataset_id': DATASET_ID, 'layer_kind': kind,
                'information_type': 'historical_satellite_observation', 'acquired_at': '2024-05-01T08:06:00Z'}
