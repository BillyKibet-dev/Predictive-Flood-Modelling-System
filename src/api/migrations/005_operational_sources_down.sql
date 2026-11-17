-- No CASCADE: external dependencies prevent rollback rather than being removed.
DROP TABLE IF EXISTS __SCHEMA__.operational_forecast_snapshot_zones;
DROP TABLE IF EXISTS __SCHEMA__.operational_forecast_snapshots;
DROP TABLE IF EXISTS __SCHEMA__.operational_zone_quality;
DROP TABLE IF EXISTS __SCHEMA__.operational_source_receipts;
DROP TABLE IF EXISTS __SCHEMA__.operational_collection_attempts;
DROP TABLE IF EXISTS __SCHEMA__.operational_source_imports;
DROP FUNCTION IF EXISTS __SCHEMA__.operational_check_ready_snapshot();
DROP FUNCTION IF EXISTS __SCHEMA__.operational_check_import_transition();
DROP FUNCTION IF EXISTS __SCHEMA__.operational_reject_evidence_mutation();
