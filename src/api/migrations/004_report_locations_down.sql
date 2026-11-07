DROP TABLE IF EXISTS report_review_events;
ALTER TABLE citizen_reports DROP CONSTRAINT IF EXISTS ck_report_location_review;
DROP INDEX IF EXISTS ix_citizen_reports_review_status;
ALTER TABLE citizen_reports
 DROP COLUMN IF EXISTS location_description,
 DROP COLUMN IF EXISTS latitude,
 DROP COLUMN IF EXISTS longitude,
 DROP COLUMN IF EXISTS location_accuracy_m,
 DROP COLUMN IF EXISTS review_status,
 DROP COLUMN IF EXISTS review_note,
 DROP COLUMN IF EXISTS reviewed_by,
 DROP COLUMN IF EXISTS reviewed_at,
 DROP COLUMN IF EXISTS review_version;
