-- Optional location and staff-review fields preserve existing anonymous clients.
ALTER TABLE citizen_reports
 ADD COLUMN IF NOT EXISTS location_description VARCHAR(250),
 ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION,
 ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION,
 ADD COLUMN IF NOT EXISTS location_accuracy_m DOUBLE PRECISION,
 ADD COLUMN IF NOT EXISTS review_status VARCHAR(20) NOT NULL DEFAULT 'New',
 ADD COLUMN IF NOT EXISTS review_note TEXT,
 ADD COLUMN IF NOT EXISTS reviewed_by INTEGER REFERENCES users(id),
 ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS review_version INTEGER NOT NULL DEFAULT 0;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='citizen_reports'::regclass AND conname='ck_report_location_review') THEN
 ALTER TABLE citizen_reports ADD CONSTRAINT ck_report_location_review CHECK (
   (latitude IS NULL) = (longitude IS NULL)
   AND (latitude IS NULL OR latitude BETWEEN -90 AND 90)
   AND (longitude IS NULL OR longitude BETWEEN -180 AND 180)
   AND (location_accuracy_m IS NULL OR (latitude IS NOT NULL AND location_accuracy_m BETWEEN 0 AND 100000))
   AND review_status IN ('New','Reviewed','ActionNeeded','Resolved') AND review_version >= 0
 ); END IF;
END $$;
CREATE TABLE IF NOT EXISTS report_review_events (
 id SERIAL PRIMARY KEY,
 report_id INTEGER NOT NULL REFERENCES citizen_reports(id),
 reviewer_id INTEGER NOT NULL REFERENCES users(id),
 previous_status VARCHAR(20) NOT NULL, status VARCHAR(20) NOT NULL,
 note TEXT, version INTEGER NOT NULL,
 created_at TIMESTAMPTZ NOT NULL,
 UNIQUE(report_id,version)
);
CREATE INDEX IF NOT EXISTS ix_report_review_events_report_id ON report_review_events(report_id);
CREATE INDEX IF NOT EXISTS ix_citizen_reports_review_status ON citizen_reports(review_status);
