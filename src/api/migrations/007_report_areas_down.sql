-- Refused by migrate_reports while any report has only a sub-county (no original zone).
DROP INDEX IF EXISTS ix_citizen_reports_area;
ALTER TABLE citizen_reports DROP CONSTRAINT IF EXISTS ck_report_area;
ALTER TABLE citizen_reports ALTER COLUMN zone_id SET NOT NULL;
ALTER TABLE citizen_reports DROP COLUMN IF EXISTS area_id;
