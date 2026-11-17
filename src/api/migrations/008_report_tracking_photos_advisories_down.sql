-- Refused by migrate_reports while advisories, tracking codes or photos exist.
DROP INDEX IF EXISTS ix_area_advisories_active;
DROP TABLE IF EXISTS area_advisories;
ALTER TABLE citizen_reports
 DROP COLUMN IF EXISTS tracking_hash,
 DROP COLUMN IF EXISTS photo_sha256,
 DROP COLUMN IF EXISTS photo_bytes;
