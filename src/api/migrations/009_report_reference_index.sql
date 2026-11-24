-- One-step status checks: a resident's single reference (FW-XXXXXX) is found by its hash.
CREATE INDEX IF NOT EXISTS ix_citizen_reports_tracking_hash ON citizen_reports(tracking_hash);
