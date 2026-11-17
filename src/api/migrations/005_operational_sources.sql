-- Phase 2: append-only source evidence; no model predictions or startup DDL.
-- __SCHEMA__ is replaced only by the validated, explicit migration runner.
CREATE TABLE IF NOT EXISTS __SCHEMA__.operational_source_imports (
 id UUID PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ,
 status VARCHAR(20) NOT NULL CHECK (status IN ('STARTED','IMPORTED','REUSED','FAILED')),
 capture_sha256 VARCHAR(64), input_reference JSONB NOT NULL,
 resumes_import_id UUID REFERENCES __SCHEMA__.operational_source_imports(id),
 error_code VARCHAR(80), result JSONB,
 CHECK (capture_sha256 IS NULL OR capture_sha256 ~ '^[0-9a-f]{64}$'),
 CHECK ((status='STARTED' AND completed_at IS NULL) OR (status<>'STARTED' AND completed_at IS NOT NULL)),
 CHECK (completed_at IS NULL OR completed_at >= started_at)
);
CREATE INDEX IF NOT EXISTS ix_operational_import_capture ON __SCHEMA__.operational_source_imports(capture_sha256);
CREATE TABLE IF NOT EXISTS __SCHEMA__.operational_collection_attempts (
 id UUID PRIMARY KEY, capture_sha256 VARCHAR(64) NOT NULL UNIQUE CHECK (capture_sha256 ~ '^[0-9a-f]{64}$'),
 readiness_sha256 VARCHAR(64) NOT NULL CHECK (readiness_sha256 ~ '^[0-9a-f]{64}$'),
 model VARCHAR(40) NOT NULL, run_initialization TIMESTAMPTZ NOT NULL,
 request_started_at TIMESTAMPTZ NOT NULL, response_received_at TIMESTAMPTZ NOT NULL,
 source_storage_completed_at TIMESTAMPTZ NOT NULL, raw_persisted_at TIMESTAMPTZ,
 http_status INTEGER CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
 body_complete BOOLEAN NOT NULL, transport_error VARCHAR(100), provider_error VARCHAR(500),
 outcome VARCHAR(30) NOT NULL CHECK (outcome IN ('ELIGIBLE','SOURCE_REJECTED','PROVIDER_FAILED')),
 source_quality VARCHAR(10) NOT NULL CHECK (source_quality IN ('PASSED','PARTIAL','FAILED')),
 target_quality VARCHAR(10) NOT NULL CHECK (target_quality IN ('PASSED','FAILED')),
 capture_reference JSONB NOT NULL, readiness_reference JSONB NOT NULL,
 capture_document JSONB NOT NULL, readiness_document JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(id,model,run_initialization)
);
CREATE INDEX IF NOT EXISTS ix_operational_attempt_run ON __SCHEMA__.operational_collection_attempts(model,run_initialization);
CREATE TABLE IF NOT EXISTS __SCHEMA__.operational_source_receipts (
 id UUID PRIMARY KEY, attempt_id UUID NOT NULL UNIQUE,
 model VARCHAR(40) NOT NULL, run_initialization TIMESTAMPTZ NOT NULL,
 source_identity_sha256 VARCHAR(64) NOT NULL CHECK (source_identity_sha256 ~ '^[0-9a-f]{64}$'),
 raw_sha256 VARCHAR(64) NOT NULL CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
 raw_bytes INTEGER NOT NULL CHECK (raw_bytes>=0), raw_reference JSONB NOT NULL,
 response_kind VARCHAR(30) NOT NULL CHECK (response_kind IN ('HTTP_SUCCESS_BODY','HTTP_ERROR_BODY','INCOMPLETE_BODY')),
 source_publication_at TIMESTAMPTZ, publication_basis VARCHAR(80),
 provenance JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 FOREIGN KEY(attempt_id,model,run_initialization) REFERENCES __SCHEMA__.operational_collection_attempts(id,model,run_initialization),
 UNIQUE(id,attempt_id), UNIQUE(id,model,run_initialization),
 CHECK (source_publication_at IS NULL OR (publication_basis IS NOT NULL AND publication_basis='independent_provider_metadata'))
);
CREATE INDEX IF NOT EXISTS ix_operational_receipt_raw_hash ON __SCHEMA__.operational_source_receipts(raw_sha256);
CREATE INDEX IF NOT EXISTS ix_operational_receipt_identity ON __SCHEMA__.operational_source_receipts(source_identity_sha256);
CREATE TABLE IF NOT EXISTS __SCHEMA__.operational_zone_quality (
 id UUID PRIMARY KEY, attempt_id UUID NOT NULL REFERENCES __SCHEMA__.operational_collection_attempts(id),
 receipt_id UUID, zone_id VARCHAR(50) NOT NULL REFERENCES __SCHEMA__.zones(id),
 requested_latitude DOUBLE PRECISION NOT NULL, requested_longitude DOUBLE PRECISION NOT NULL,
 returned_latitude DOUBLE PRECISION, returned_longitude DOUBLE PRECISION, returned_elevation DOUBLE PRECISION,
 source_quality VARCHAR(10) NOT NULL CHECK (source_quality IN ('PASSED','PARTIAL','FAILED')),
 target_quality VARCHAR(10) NOT NULL CHECK (target_quality IN ('PASSED','FAILED')),
 document JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(attempt_id,zone_id), UNIQUE(id,receipt_id,zone_id),
 FOREIGN KEY(receipt_id,attempt_id) REFERENCES __SCHEMA__.operational_source_receipts(id,attempt_id),
 CHECK (target_quality<>'PASSED' OR source_quality IN ('PASSED','PARTIAL'))
);
CREATE INDEX IF NOT EXISTS ix_operational_qc_zone ON __SCHEMA__.operational_zone_quality(zone_id);
CREATE TABLE IF NOT EXISTS __SCHEMA__.operational_forecast_snapshots (
 id UUID PRIMARY KEY, identity_sha256 VARCHAR(64) NOT NULL UNIQUE CHECK (identity_sha256 ~ '^[0-9a-f]{64}$'),
 receipt_id UUID NOT NULL, model VARCHAR(40) NOT NULL, run_initialization TIMESTAMPTZ NOT NULL,
 issue_date DATE NOT NULL, candidate_issue_at TIMESTAMPTZ NOT NULL,
 target_start TIMESTAMPTZ NOT NULL, target_end TIMESTAMPTZ NOT NULL,
 status VARCHAR(30) NOT NULL CHECK (status='READY_AS_RECORDED'),
 policy JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 FOREIGN KEY(receipt_id,model,run_initialization) REFERENCES __SCHEMA__.operational_source_receipts(id,model,run_initialization),
 UNIQUE(id,receipt_id), UNIQUE(receipt_id,candidate_issue_at,target_start,target_end),
 CHECK ((candidate_issue_at AT TIME ZONE 'Africa/Nairobi')::date=issue_date),
 CHECK ((candidate_issue_at AT TIME ZONE 'Africa/Nairobi')::time=TIME '06:00'),
 CHECK ((target_start AT TIME ZONE 'Africa/Nairobi')::date=issue_date+1),
 CHECK ((target_start AT TIME ZONE 'Africa/Nairobi')::time=TIME '00:00'),
 CHECK (target_end=target_start+INTERVAL '24 hours'), CHECK (run_initialization<=candidate_issue_at)
);
CREATE TABLE IF NOT EXISTS __SCHEMA__.operational_forecast_snapshot_zones (
 snapshot_id UUID NOT NULL, receipt_id UUID NOT NULL, zone_id VARCHAR(50) NOT NULL,
 quality_id UUID NOT NULL, PRIMARY KEY(snapshot_id,zone_id),
 FOREIGN KEY(snapshot_id,receipt_id) REFERENCES __SCHEMA__.operational_forecast_snapshots(id,receipt_id),
 FOREIGN KEY(quality_id,receipt_id,zone_id) REFERENCES __SCHEMA__.operational_zone_quality(id,receipt_id,zone_id)
);

CREATE OR REPLACE FUNCTION __SCHEMA__.operational_reject_evidence_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'Operational source evidence is append-only; use reviewed migration rollback for removal';
END $$;

-- Import journals have immutable context and one STARTED -> terminal transition.
CREATE OR REPLACE FUNCTION __SCHEMA__.operational_check_import_transition() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP<>'UPDATE' THEN RAISE EXCEPTION 'Import journal entries cannot be removed'; END IF;
 IF OLD.status<>'STARTED' OR NEW.status NOT IN ('IMPORTED','REUSED','FAILED') OR
    (to_jsonb(NEW)-ARRAY['status','completed_at','error_code','result']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['status','completed_at','error_code','result']) THEN
   RAISE EXCEPTION 'Invalid operational import journal transition';
 END IF;
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION __SCHEMA__.operational_check_ready_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE snapshot_key UUID; s RECORD; count_zones INTEGER; zone_ids TEXT[];
BEGIN
 IF TG_TABLE_NAME='operational_forecast_snapshots' THEN snapshot_key:=NEW.id;
 ELSE snapshot_key:=NEW.snapshot_id; END IF;
 SELECT sn.*, a.outcome, a.http_status, a.body_complete, a.response_received_at,
        a.source_storage_completed_at, r.source_publication_at,
        a.capture_document->'policy' AS source_policy, a.readiness_document->>'snapshot_readiness' AS source_readiness
 INTO s FROM __SCHEMA__.operational_forecast_snapshots sn
 JOIN __SCHEMA__.operational_source_receipts r ON r.id=sn.receipt_id
 JOIN __SCHEMA__.operational_collection_attempts a ON a.id=r.attempt_id
 WHERE sn.id=snapshot_key;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF s.outcome<>'ELIGIBLE' OR s.http_status<>200 OR NOT s.body_complete OR
    s.model<>'ecmwf_ifs' OR s.response_received_at>s.candidate_issue_at OR
    s.source_storage_completed_at>s.candidate_issue_at OR
    (s.source_publication_at IS NOT NULL AND (s.source_publication_at>s.response_received_at OR s.source_publication_at>s.candidate_issue_at)) OR
    s.source_readiness IS DISTINCT FROM 'READY_FOR_SHADOW_SNAPSHOT' OR s.policy IS DISTINCT FROM s.source_policy OR
    s.candidate_issue_at IS DISTINCT FROM (s.policy->>'candidate_issue_at')::timestamptz OR
    s.target_start IS DISTINCT FROM (s.policy->>'target_start')::timestamptz OR
    s.target_end IS DISTINCT FROM (s.policy->>'target_end')::timestamptz OR
    (s.policy->>'contract_version') IS DISTINCT FROM 'openmeteo-ifs-shadow-v1' OR
    s.policy->>'max_run_age_hours' IS NULL OR
    EXTRACT(EPOCH FROM (s.candidate_issue_at-s.run_initialization))/3600 > (s.policy->>'max_run_age_hours')::numeric THEN
   RAISE EXCEPTION 'Ready snapshot requires eligible original source and cutoff evidence';
 END IF;
 SELECT count(*), array_agg(m.zone_id::text ORDER BY m.zone_id) INTO count_zones,zone_ids
 FROM __SCHEMA__.operational_forecast_snapshot_zones m
 JOIN __SCHEMA__.operational_zone_quality q ON q.id=m.quality_id AND q.receipt_id=m.receipt_id AND q.zone_id=m.zone_id
 WHERE m.snapshot_id=snapshot_key AND q.target_quality='PASSED' AND q.source_quality IN ('PASSED','PARTIAL');
 IF count_zones<>8 OR zone_ids IS DISTINCT FROM ARRAY['cbd','dagoretti','embakasi','kasarani','kibera','mathare','ruaraka','westlands']::text[] THEN
   RAISE EXCEPTION 'Ready snapshot requires all eight matching eligible zones';
 END IF;
 RETURN NULL;
END $$;

-- Names are scoped to tables; every trigger/function uses the explicit schema.
DO $$ DECLARE name TEXT; BEGIN
 FOREACH name IN ARRAY ARRAY['operational_collection_attempts','operational_source_receipts','operational_zone_quality','operational_forecast_snapshots','operational_forecast_snapshot_zones'] LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS immutable_source_rows ON __SCHEMA__.%I',name);
  EXECUTE format('CREATE TRIGGER immutable_source_rows BEFORE UPDATE OR DELETE ON __SCHEMA__.%I FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.operational_reject_evidence_mutation()',name);
  EXECUTE format('DROP TRIGGER IF EXISTS immutable_source_truncate ON __SCHEMA__.%I',name);
  EXECUTE format('CREATE TRIGGER immutable_source_truncate BEFORE TRUNCATE ON __SCHEMA__.%I FOR EACH STATEMENT EXECUTE FUNCTION __SCHEMA__.operational_reject_evidence_mutation()',name);
 END LOOP;
END $$;
DROP TRIGGER IF EXISTS import_journal_transition ON __SCHEMA__.operational_source_imports;
CREATE TRIGGER import_journal_transition BEFORE UPDATE OR DELETE ON __SCHEMA__.operational_source_imports
 FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.operational_check_import_transition();
DROP TRIGGER IF EXISTS import_journal_truncate ON __SCHEMA__.operational_source_imports;
CREATE TRIGGER import_journal_truncate BEFORE TRUNCATE ON __SCHEMA__.operational_source_imports
 FOR EACH STATEMENT EXECUTE FUNCTION __SCHEMA__.operational_reject_evidence_mutation();
DROP TRIGGER IF EXISTS ready_snapshot_complete ON __SCHEMA__.operational_forecast_snapshots;
CREATE CONSTRAINT TRIGGER ready_snapshot_complete AFTER INSERT ON __SCHEMA__.operational_forecast_snapshots
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.operational_check_ready_snapshot();
DROP TRIGGER IF EXISTS ready_members_complete ON __SCHEMA__.operational_forecast_snapshot_zones;
CREATE CONSTRAINT TRIGGER ready_members_complete AFTER INSERT ON __SCHEMA__.operational_forecast_snapshot_zones
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.operational_check_ready_snapshot();
