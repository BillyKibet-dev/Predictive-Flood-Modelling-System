-- Citizens report under the 17 sub-counties shown on the map, not the original eight model
-- zones. Older reports keep their zone; new reports carry a sub-county area instead.
ALTER TABLE citizen_reports ADD COLUMN IF NOT EXISTS area_id VARCHAR(80);
ALTER TABLE citizen_reports ALTER COLUMN zone_id DROP NOT NULL;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='citizen_reports'::regclass AND conname='ck_report_area') THEN
 ALTER TABLE citizen_reports ADD CONSTRAINT ck_report_area CHECK (zone_id IS NOT NULL OR area_id IS NOT NULL);
 END IF;
END $$;
-- Older reports with a pin get the sub-county that contains it (when the outlines are loaded).
DO $$ BEGIN
 IF to_regclass('administrative_boundaries') IS NOT NULL THEN
  UPDATE citizen_reports r SET area_id = b.id FROM administrative_boundaries b
   WHERE r.area_id IS NULL AND r.latitude IS NOT NULL AND b.admin_level = 2
     AND b.id LIKE 'nairobi-subcounty-%'
     AND ST_Covers(b.geometry, ST_SetSRID(ST_MakePoint(r.longitude, r.latitude), 4326));
 END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_citizen_reports_area ON citizen_reports(area_id);
