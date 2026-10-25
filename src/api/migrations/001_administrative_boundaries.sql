-- Applied explicitly by src.scripts.load_boundaries, not during API startup.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS administrative_boundaries (
    id VARCHAR(80) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    admin_level SMALLINT NOT NULL CHECK (admin_level BETWEEN 0 AND 5),
    country_code VARCHAR(3) NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_license TEXT NOT NULL,
    source_year VARCHAR(20) NOT NULL,
    source_feature_id VARCHAR(100) NOT NULL,
    geometry geometry(MULTIPOLYGON, 4326) NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_boundary_nonempty CHECK (NOT ST_IsEmpty(geometry)),
    CONSTRAINT ck_boundary_valid CHECK (ST_IsValid(geometry)),
    CONSTRAINT ck_boundary_wgs84_bounds CHECK (
        ST_XMin(Box3D(geometry)) >= -180 AND ST_XMax(Box3D(geometry)) <= 180
        AND ST_YMin(Box3D(geometry)) >= -90 AND ST_YMax(Box3D(geometry)) <= 90
    )
);

CREATE INDEX IF NOT EXISTS ix_administrative_boundaries_geometry
    ON administrative_boundaries USING GIST (geometry);
