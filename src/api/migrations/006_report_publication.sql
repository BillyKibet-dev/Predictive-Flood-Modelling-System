-- Staff choice to show a checked report on the public map for 24 hours after it was reported.
-- Separate from the review status: "Reviewed" means looked at, not published.
ALTER TABLE citizen_reports
 ADD COLUMN IF NOT EXISTS public_visible BOOLEAN NOT NULL DEFAULT false,
 ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS published_by INTEGER REFERENCES users(id);
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='citizen_reports'::regclass AND conname='ck_report_publication') THEN
 ALTER TABLE citizen_reports ADD CONSTRAINT ck_report_publication CHECK (
   NOT public_visible OR (latitude IS NOT NULL AND published_at IS NOT NULL AND published_by IS NOT NULL)
 ); END IF;
END $$;
ALTER TABLE report_review_events ADD COLUMN IF NOT EXISTS public_visible BOOLEAN;
CREATE INDEX IF NOT EXISTS ix_citizen_reports_public_recent ON citizen_reports(public_visible, timestamp);
