-- Residents can check a report's status with its reference and a private tracking code
-- (only its hash is stored); a report may carry one photo, re-encoded without metadata and
-- shown to staff only; officers can post short time-limited advisories for an area.
ALTER TABLE citizen_reports
 ADD COLUMN IF NOT EXISTS tracking_hash VARCHAR(64),
 ADD COLUMN IF NOT EXISTS photo_sha256 VARCHAR(64),
 ADD COLUMN IF NOT EXISTS photo_bytes INTEGER;
CREATE TABLE IF NOT EXISTS area_advisories (
 id SERIAL PRIMARY KEY,
 area_id VARCHAR(80) NOT NULL,
 place_label VARCHAR(120),
 latitude DOUBLE PRECISION,
 longitude DOUBLE PRECISION,
 message VARCHAR(280) NOT NULL,
 level VARCHAR(20) NOT NULL,
 created_by INTEGER NOT NULL REFERENCES users(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 expires_at TIMESTAMPTZ NOT NULL,
 withdrawn_at TIMESTAMPTZ,
 withdrawn_by INTEGER REFERENCES users(id),
 CONSTRAINT ck_advisory_level CHECK (level IN ('Advice', 'Warning')),
 CONSTRAINT ck_advisory_pin CHECK ((latitude IS NULL) = (longitude IS NULL)),
 CONSTRAINT ck_advisory_expiry CHECK (expires_at > created_at),
 CONSTRAINT ck_advisory_withdrawal CHECK ((withdrawn_at IS NULL) = (withdrawn_by IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_area_advisories_active ON area_advisories(expires_at, withdrawn_at);
