-- Run only after the explicit CLI has checked emptiness or the operator has
-- explicitly approved data loss. Never drops legacy tables or alert history.
DROP TABLE IF EXISTS proxy_v1_predictions;
DROP TABLE IF EXISTS proxy_v1_runs;
DROP TABLE IF EXISTS proxy_v1_zone_terrain;
