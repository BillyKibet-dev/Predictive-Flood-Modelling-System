-- Additive research-only source store. Never executed by API startup.
CREATE TABLE IF NOT EXISTS environmental_sources (
 id VARCHAR(60) PRIMARY KEY, name VARCHAR(150) NOT NULL,
 source_kind VARCHAR(40) NOT NULL, temporal_resolution VARCHAR(20) NOT NULL,
 approval_basis VARCHAR(100) NOT NULL, provenance JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS environmental_datasets (
 id VARCHAR(64) PRIMARY KEY, source_id VARCHAR(60) NOT NULL REFERENCES environmental_sources(id),
 source_sha256 VARCHAR(64) NOT NULL, recipe_version VARCHAR(60) NOT NULL,
 imported_at TIMESTAMPTZ NOT NULL, start_at TIMESTAMPTZ, end_at TIMESTAMPTZ,
 row_count INTEGER NOT NULL CHECK (row_count >= 0),
 observation_count INTEGER NOT NULL CHECK (observation_count >= 0),
 qc_summary JSON NOT NULL, provenance JSON NOT NULL,
 CHECK ((start_at IS NULL AND end_at IS NULL) OR (start_at IS NOT NULL AND end_at IS NOT NULL AND end_at > start_at))
);
CREATE INDEX IF NOT EXISTS ix_environmental_datasets_source_id ON environmental_datasets(source_id);
CREATE TABLE IF NOT EXISTS environmental_observations (
 id VARCHAR(64) PRIMARY KEY, dataset_id VARCHAR(64) NOT NULL REFERENCES environmental_datasets(id),
 zone_id VARCHAR(50) NOT NULL REFERENCES zones(id), variable VARCHAR(60) NOT NULL,
 observed_at TIMESTAMPTZ NOT NULL, bin_end_at TIMESTAMPTZ NOT NULL,
 data_available_at TIMESTAMPTZ, value DOUBLE PRECISION, unit VARCHAR(20) NOT NULL,
 original_value DOUBLE PRECISION, original_unit VARCHAR(20) NOT NULL, quality_flags JSON NOT NULL,
 UNIQUE(dataset_id, zone_id, variable, observed_at),
 CHECK (bin_end_at > observed_at),
 CHECK (data_available_at IS NULL OR data_available_at >= observed_at)
);
CREATE INDEX IF NOT EXISTS ix_environmental_observations_dataset_id ON environmental_observations(dataset_id);
CREATE INDEX IF NOT EXISTS ix_environmental_observations_zone_id ON environmental_observations(zone_id);
CREATE INDEX IF NOT EXISTS ix_environmental_observations_variable ON environmental_observations(variable);
CREATE INDEX IF NOT EXISTS ix_environmental_observations_observed_at ON environmental_observations(observed_at);
CREATE TABLE IF NOT EXISTS environmental_ingestions (
 id VARCHAR(36) PRIMARY KEY, source_id VARCHAR(60) NOT NULL,
 dataset_id VARCHAR(64) REFERENCES environmental_datasets(id),
 started_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ,
 status VARCHAR(20) NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','REUSED','REJECTED','FAILED')),
 error_code VARCHAR(80), summary JSON NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_environmental_ingestions_source_id ON environmental_ingestions(source_id);
