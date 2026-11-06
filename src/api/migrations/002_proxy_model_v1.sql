-- Explicit, transactional research v1 upgrade. Existing legacy tables are untouched.
CREATE TABLE IF NOT EXISTS proxy_v1_zone_terrain (
    zone_id VARCHAR(50) NOT NULL REFERENCES zones(id),
    terrain_version VARCHAR(64) NOT NULL,
    slope_degrees DOUBLE PRECISION NOT NULL CHECK (slope_degrees BETWEEN 0 AND 90),
    ndvi DOUBLE PRECISION NOT NULL CHECK (ndvi BETWEEN -1 AND 1),
    impervious_fraction DOUBLE PRECISION NOT NULL CHECK (impervious_fraction BETWEEN 0 AND 1),
    vegetation_fraction DOUBLE PRECISION NOT NULL CHECK (vegetation_fraction BETWEEN 0 AND 1),
    provenance JSON NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (zone_id, terrain_version)
);

CREATE TABLE IF NOT EXISTS proxy_v1_runs (
    id VARCHAR(64) PRIMARY KEY,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    request_hash VARCHAR(64) NOT NULL,
    mode VARCHAR(32) NOT NULL CHECK (mode IN ('live', 'historical_replay')),
    model_version VARCHAR(80) NOT NULL,
    model_task_type VARCHAR(40) NOT NULL CHECK (model_task_type = 'next_day_proxy_risk'),
    model_artifact_hash VARCHAR(64),
    source_digest VARCHAR(64) NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    input_date DATE NOT NULL,
    forecast_target_date DATE NOT NULL CHECK (forecast_target_date > input_date),
    forecast_horizon VARCHAR(40) NOT NULL,
    data_as_of TIMESTAMPTZ,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL,
    reason_codes JSON NOT NULL,
    source_metadata JSON NOT NULL,
    limitation_flags JSON NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_proxy_v1_runs_input_date ON proxy_v1_runs(input_date);
CREATE INDEX IF NOT EXISTS ix_proxy_v1_runs_forecast_target_date ON proxy_v1_runs(forecast_target_date);

CREATE TABLE IF NOT EXISTS proxy_v1_predictions (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES proxy_v1_runs(id),
    zone_id VARCHAR(50) NOT NULL REFERENCES zones(id),
    status VARCHAR(32) NOT NULL,
    reason_codes JSON NOT NULL,
    risk_class INTEGER CHECK (risk_class IS NULL OR risk_class BETWEEN 0 AND 3),
    risk_level VARCHAR(20) NOT NULL,
    model_class_score DOUBLE PRECISION CHECK (model_class_score IS NULL OR model_class_score BETWEEN 0 AND 1),
    proxy_class_scores JSON,
    feature_hash VARCHAR(64),
    terrain_version VARCHAR(64),
    data_as_of TIMESTAMPTZ,
    freshness VARCHAR(32) NOT NULL,
    source_metadata JSON NOT NULL,
    limitation_flags JSON NOT NULL,
    CONSTRAINT uq_v1_run_zone UNIQUE(run_id, zone_id),
    CONSTRAINT ck_v1_result_status CHECK (
        (status = 'SUCCESS' AND risk_class IS NOT NULL AND proxy_class_scores IS NOT NULL)
        OR (status <> 'SUCCESS' AND risk_class IS NULL AND model_class_score IS NULL AND proxy_class_scores IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS ix_proxy_v1_predictions_run_id ON proxy_v1_predictions(run_id);
CREATE INDEX IF NOT EXISTS ix_proxy_v1_predictions_zone_id ON proxy_v1_predictions(zone_id);
