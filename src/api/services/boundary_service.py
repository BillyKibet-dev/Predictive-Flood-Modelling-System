"""Validate administrative GeoJSON and store/query native PostGIS geometries."""
import json
import math
import re
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BOUNDARY_PATH = PROJECT_ROOT / "data/boundaries/nairobi_county.geojson"
DEFAULT_SUBCOUNTY_PATH = PROJECT_ROOT / "data/boundaries/nairobi_subcounties.geojson"
MIGRATION_PATH = PROJECT_ROOT / "src/api/migrations/001_administrative_boundaries.sql"
PROPERTY_LIMITS = {
    "name": 100, "country_code": 3, "source": 500, "source_url": 2000,
    "source_license": 200, "source_year": 20, "source_feature_id": 100,
}


class BoundariesUnavailable(Exception):
    """The optional spatial schema has not been initialized."""


def validate_feature_collection(document: dict) -> list[dict]:
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("The boundary collection must contain at least one feature")
    if "crs" in document:
        raise ValueError("Use RFC 7946 longitude/latitude coordinates without a crs member")

    identifiers = set()
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("Every boundary must be a GeoJSON Feature")
        identifier = feature.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", identifier):
            raise ValueError("Boundary IDs must be lowercase letters, digits, underscores or hyphens (max 80)")
        if identifier in identifiers:
            raise ValueError(f"Duplicate boundary ID: {identifier}")
        identifiers.add(identifier)
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(f"Missing properties for {identifier}")
        for key, limit in PROPERTY_LIMITS.items():
            value = properties.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError(f"Invalid {key} for {identifier}")
        if not re.fullmatch(r"[A-Z]{3}", properties["country_code"]):
            raise ValueError("country_code must be a three-letter ISO code")
        if type(properties.get("admin_level")) is not int or not 0 <= properties["admin_level"] <= 5:
            raise ValueError("admin_level must be an integer between 0 and 5")

        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"Expected a Polygon or MultiPolygon for {identifier}")
        if "crs" in geometry or "crs" in feature:
            raise ValueError("Only RFC 7946 longitude/latitude GeoJSON is supported")
        coordinates = geometry.get("coordinates")
        polygons = [coordinates] if geometry["type"] == "Polygon" else coordinates
        if not isinstance(polygons, list) or not polygons:
            raise ValueError("Empty boundary geometry")
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                raise ValueError("A polygon must contain at least one ring")
            for ring in polygon:
                if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError("Polygon rings must be closed and contain at least four positions")
                for position in ring:
                    if not isinstance(position, list) or len(position) != 2:
                        raise ValueError("Expected two-dimensional [longitude, latitude] positions")
                    if any(type(value) not in (int, float) or not math.isfinite(value) for value in position):
                        raise ValueError("Coordinates must be finite numbers")
                    if not -180 <= position[0] <= 180 or not -90 <= position[1] <= 90:
                        raise ValueError("Coordinates must use WGS84 longitude/latitude ranges")
    return features


def load_boundaries(connection, path: Path = DEFAULT_BOUNDARY_PATH) -> list[str]:
    """Apply the spatial migration and upsert a collection in the caller's transaction."""
    features = validate_feature_collection(json.loads(Path(path).read_text(encoding="utf-8")))
    connection.execute(text(MIGRATION_PATH.read_text(encoding="utf-8")))
    for feature in features:
        values = {key: feature["properties"][key] for key in PROPERTY_LIMITS}
        values.update(id=feature["id"], admin_level=feature["properties"]["admin_level"],
                      geometry=json.dumps(feature["geometry"], allow_nan=False))
        connection.execute(text("""
            INSERT INTO administrative_boundaries
                (id, name, admin_level, country_code, source, source_url,
                 source_license, source_year, source_feature_id, geometry)
            VALUES
                (:id, :name, :admin_level, :country_code, :source, :source_url,
                 :source_license, :source_year, :source_feature_id,
                 ST_Multi(ST_ForcePolygonCCW(ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326))))
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name, admin_level = EXCLUDED.admin_level,
                country_code = EXCLUDED.country_code, source = EXCLUDED.source,
                source_url = EXCLUDED.source_url, source_license = EXCLUDED.source_license,
                source_year = EXCLUDED.source_year, source_feature_id = EXCLUDED.source_feature_id,
                geometry = EXCLUDED.geometry, imported_at = CURRENT_TIMESTAMP
        """), values)
    return [feature["id"] for feature in features]


def get_boundaries(db, boundary_id: str | None = None) -> dict:
    if db.bind.dialect.name != "postgresql" or not db.execute(text(
        "SELECT to_regclass('administrative_boundaries')"
    )).scalar():
        raise BoundariesUnavailable()
    rows = db.execute(text("""
        SELECT b.id, b.name, b.admin_level, b.country_code, b.source, b.source_url,
               b.source_license, b.source_year, b.source_feature_id,
               ST_AsGeoJSON(ST_ForcePolygonCCW(b.geometry), 9, 0) AS geometry,
               CASE WHEN b.admin_level = 2 THEN COALESCE((
                   SELECT json_agg(z.id ORDER BY z.id) FROM zones z
                   WHERE ST_Covers(b.geometry, ST_SetSRID(ST_MakePoint(z.longitude, z.latitude), 4326))
               ), '[]'::json) ELSE '[]'::json END AS monitoring_zone_ids
        FROM administrative_boundaries b
        WHERE (:boundary_id IS NULL OR b.id = :boundary_id)
        ORDER BY b.id
    """), {"boundary_id": boundary_id}).mappings()
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "id": row["id"], "geometry": json.loads(row["geometry"]),
             "properties": {key: row[key] for key in (*PROPERTY_LIMITS, "admin_level", "monitoring_zone_ids")}}
            for row in rows
        ],
    }
