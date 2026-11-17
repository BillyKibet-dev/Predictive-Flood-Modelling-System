DROP INDEX IF EXISTS ix_citizen_reports_public_recent;
ALTER TABLE IF EXISTS report_review_events DROP COLUMN IF EXISTS public_visible;
ALTER TABLE citizen_reports DROP CONSTRAINT IF EXISTS ck_report_publication;
ALTER TABLE citizen_reports
 DROP COLUMN IF EXISTS public_visible,
 DROP COLUMN IF EXISTS published_at,
 DROP COLUMN IF EXISTS published_by;
