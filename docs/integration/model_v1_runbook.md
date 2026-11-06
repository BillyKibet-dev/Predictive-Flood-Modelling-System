# v1 research replay runbook

Scope: the selected native XGBoost v1 model, verified historical feature construction, separate research persistence and explicit frontend display. **Live v1 predictions and emergency alert delivery remain unavailable.** Do not start Prompt2, substitute the experimental candidate, retrain, provision cloud resources or promote this model operationally as part of these steps.

## Local package and environment

Application prerequisites remain `requirements.txt` and the existing privately configured PostgreSQL/PostGIS connection. Do not print environment files or connection strings. The application Python environment retains its older model libraries for legacy rollback. In a separate environment:

```powershell
.venv/Scripts/python.exe -m venv .venv-model-v1
.venv-model-v1/Scripts/python.exe -m pip install -r requirements-model-v1.txt
```

This pins native XGBoost3.1.3/NumPy1.26.4/SciPy1.17.1. It does not install sklearn, unpickle v1 joblib or train a classifier. Actual integration was verified on Python3.12.1; the research producer's Python3.13.5/sklearn1.8.0 environment is recorded as provenance rather than assumed necessary for native inference.

Keep supplied `codex-handoff/` local and ignored. Install only the approved native package and small research inputs:

```powershell
.venv/Scripts/python.exe -m src.scripts.package_model_v1 --handoff codex-handoff --source-dir "PATH_TO_RECOVERED_RESEARCH_FILES"
```

The recovered-source directory must contain the exact nine files listed in `src/modeling/v1/package_manifest.json`:

- `NairobiFloodWatch_zone_daily_integrated_2016_2025.csv`
- `NairobiFloodWatch_frozen_test_2024_2025.csv`
- `CHIRPS_Nairobi_zones_2016_2025.csv`
- `zone_terrain_features.csv`
- `NairobiFloodWatch_data_quality_manifest.json`
- `weather_by_zone_provenance.json`
- `NairobiFloodWatch.ipynb`
- `cbd_2024.csv`
- `cbd_2024.json`

These were recovered read-only from the user's connected project dataset/research notebook. Their integrated source hash exactly matches the selected experiment. Do not replace them with older single-point CSVs. A 114MB all-zone hourly archive and original UNOSAT GIS archive are not required for this pathway. All selected source files are environmental data; preserve applicable source licence/metadata when redistributing. Underlying terrain reduction metadata remains incomplete.

The installer verifies **all hashes and byte sizes before copying each package**, refuses to overwrite a different installed version and uses atomic per-file replacement. Default destinations are ignored `models/nextday-proxy-v1/` and `data/model_v1/`; small trusted metadata stays versioned under `src/modeling/v1/`. It creates a local source manifest with import time, separate from unknown original publication times. Never commit raw exports, trained binaries, credentials or large handoff files blindly.

Configuration names, with safe values in `.env.example`:

```text
MODEL_V1_DIR=models/nextday-proxy-v1
MODEL_V1_DATA_DIR=data/model_v1
MODEL_V1_PYTHON=.venv-model-v1/Scripts/python.exe
AUTO_CREATE_LEGACY_TABLES=false
LEGACY_SCHEDULER_ENABLED=false
```

On another OS, set `MODEL_V1_PYTHON` to that isolated environment's executable (e.g. `.venv-model-v1/bin/python`). No live source adapter becomes enabled through these settings. The native worker verifies artifact bytes, schema, objective, class count,496 rounds, runtime version and score shape. Missing/corrupt dependencies or files fail closed with a reason, leaving other API features available.

## Explicit additive database migration

Schema upgrades are not performed on API import/startup. `ProxyV1Base` metadata is separate from legacy ORM metadata. The migration creates only:

| Table | Purpose |
| --- | --- |
| `proxy_v1_zone_terrain` | Immutable per-zone values/version/source provenance and import time |
| `proxy_v1_runs` | Deterministic identity, idempotency key, mode, artifact/source hashes, context, execution/status and limitations |
| `proxy_v1_predictions` | Per-zone status/reasons, nullable class/scores, feature hash, freshness and source metadata |

Use only an approved database/schema with existing monitoring zones. The SQL is additive and transactional; legacy predictions, zones, reports, users, alert history and spatial geometries are preserved:

```powershell
.venv/Scripts/python.exe -m src.scripts.migrate_model_v1 --schema public
```

If prerequisites/permissions are missing the command fails and rolls back; it does not create a database or seed default users. Do not use `init_db.py` as an automatic migration substitute: that older script seeds credentials and triggers legacy inference. For validation use disposable schemas/databases and fixtures, not production records.

## Manual research replay

With the explicit migration applied in the approved local or isolated schema:

```powershell
.venv/Scripts/python.exe -m src.scripts.run_model_v1 --schema public --input-date 2024-04-30 --issued-at 2024-05-01T00:00:00+03:00 --idempotency-key research-v1-2024-04-30-all
```

The default mode is `historical_replay`; use repeatable `--zone cbd --zone mathare` to restrict the configured monitoring zones. The command builds each eligible zone's own features, persists verified terrain versions, executes a batch through the pinned native worker and writes run/results atomically. The reference date is a **hindcast**. Neither CHIRPS nor ERA5 is claimed to have been published at simulated issue time. No v1 alert records or external notifications are created.

Repeat the identical request/key to obtain the original stored run with `idempotent_replay=true`. A key reused for a different input/date/zone-set/artifact/source identity is rejected. Changing the verified source/model bytes changes identity rather than silently overwriting results. Missing zone inputs yield their own Unknown/unavailable record, never another zone's score. Live requests record unavailable status; current forecasts cannot be enabled by choosing a different date or copying old data.

An identical scientific run cannot acquire a second, untracked explicit key: use its original persisted key, or omit the key to look up the deterministic identity. A different explicit alias returns409. Dates must have a representable following calendar day; invalid boundary dates return422 rather than failing during arithmetic.

The run CLI's JSON is research metadata/environmental class outputs, not observed flood truth. Avoid publishing unrelated database records or credentials when recording evidence. Tests also verify the real April30 inputs to May1 target in an isolated PostgreSQL schema, including duplicate run/rollback behavior; exact evidence is in `model_v1_validation.md`.

## API and React use

Run the existing API and frontend locally:

```powershell
.venv/Scripts/python.exe -m uvicorn src.api.main:app --port 8000
# Separate terminal, dashboard/:
npm.cmd start
```

Safe startup defaults create no schema and schedule no inference. Old read endpoints remain available. Selected v1 routes:

| Method/path | Purpose |
| --- | --- |
| `GET /api/v1/model` | Artifact/runtime availability, exact class/schema count, stored frozen proxy evaluation and live blockers |
| `GET /api/v1/dashboard` | Live/unavailable per-zone status; no historical fallback |
| `GET /api/v1/dashboard?mode=historical_replay&input_date=2024-04-30` | Explicit stored hindcast snapshot, including Unknown for absent zones |
| `GET /api/v1/predictions?zone_id=cbd&forecast_target_date=2024-05-01&mode=historical_replay` | Typed, paginated research history; input-date filter also supported |
| `POST /api/v1/predictions/run` | Admin JWT only, same validated context/zone IDs/idempotency semantics as CLI; no paths/training/deployment |

See `/docs` or `/openapi.json` for schemas/examples. Example request body (authenticate privately; do not include a token in documentation):

```json
{
  "mode": "historical_replay",
  "input_date": "2024-04-30",
  "issued_at": "2024-05-01T00:00:00+03:00",
  "zone_ids": ["cbd", "mathare"],
  "idempotency_key": "research-v1-2024-04-30-two-zones"
}
```

Failure responses distinguish401 unauthenticated,403 unauthorized role,404 unknown monitoring zones,409 conflicting identity,422 invalid temporal/schema input and503 missing/unavailable storage. A safe successful HTTP response can still contain `INSUFFICIENT_DATA`, `STALE_DATA` or `MODEL_UNAVAILABLE` research results; clients must inspect status and nullable scores, not just HTTP200.

The frontend preserves legacy as its initial view. Select **v1 live status** for explicit unavailable state, or **historical replay** plus input date. Risk cards/map popups show target date, simulated issue, actual output time, mode and source freshness. Missing/error/stale results show Unknown. Failed requests can retain only the same view/date's previous successful snapshot; another mode/date's data must not leak into the selection. Administrative fills are highest monitored proxy class summaries, never measured flood depth. Model/health panels read v1 metadata; no static AWS uptime or invented training/threshold-save success is presented as live behavior. Other mock auth/user-management workflows remain explicitly outside this integration.

## Tests and reproducible verification

The application dependency pins and legacy artifacts stay intact. Run from repository root:

```powershell
# Isolated SQLite/temporary-file tests; excludes the old synthetic classifier-fitting diagnostic.
.venv/Scripts/python.exe -m pytest tests/ -k 'not reference_refit' -q

# Also enable existing/new native PostgreSQL tests in disposable schemas:
$env:RUN_POSTGIS_TESTS = '1'
.venv/Scripts/python.exe -m pytest tests/ -k 'not reference_refit' -q
Remove-Item Env:RUN_POSTGIS_TESTS

# From dashboard/:
npm.cmd test
npm.cmd run build
```

The native v1 test flag is independent of the earlier PostGIS flag. To run **all** native checks, set both before pytest:

```powershell
$env:RUN_POSTGIS_TESTS = '1'
$env:RUN_MODEL_V1_POSTGRES_TESTS = '1'
.venv/Scripts/python.exe -m pytest tests/ -k 'not reference_refit' -q
Remove-Item Env:RUN_POSTGIS_TESTS
Remove-Item Env:RUN_MODEL_V1_POSTGRES_TESTS
```

An automated full-source/frozen-score verification plus real isolated PostgreSQL replay is also available:

```powershell
.venv/Scripts/python.exe -m src.scripts.verify_model_v1 --postgres-replay --output "$env:TEMP/model-v1-verification.json" --api-samples "$env:TEMP/model-v1-api-samples.json"
# From repository root after the frontend build; Chrome/Node must be available:
node dashboard/scripts/verifyProxyUI.mjs
```

The verifier creates and removes only its UUID-named schema and writes aggregate JSON; it neither modifies application history nor runs training. Omit `--postgres-replay` for offline feature/model verification only. The browser harness uses clearly synthetic read fixtures by default; an optional first argument supplies captured real model/API JSON, as used for the recorded integration screenshots. It blocks all writes and stubs third-party network/tile traffic. Set `CHROME_PATH` if Chrome is installed elsewhere. See the validation record for the distinction between real API data, deliberate outage injection and synthetic test fixtures.

Real-artifact/reference tests require the approved ignored model/source package and isolated runtime. A fresh clone without them will explicitly skip those particular tests; unit fixtures still validate failure contracts. Native tests require PostgreSQL with PostGIS already enabled and permission to create/drop their UUID-named schemas. They never drop or rewrite application tables. Environment-specific process-spawn restrictions can prevent Node/esbuild/Chrome execution; the validation record distinguishes those restrictions from assertion failures and records any permitted retest.

## Rollback and operational gaps

- Keep the legacy model/scaler/feature files and old table/API contracts unchanged. Select legacy in the frontend or revert the integration code commits to return to the preceding UI. Reverting code does not require deleting any old or new data.
- Stop the opt-in legacy scheduler before changing worker configuration. It uses a PostgreSQL advisory lock plus saved UTC-hour deduplication; v1 has no automatic schedule. Do not enable one scheduler per API worker expecting independently valid hourly v1 forecasts.
- The down migration targets only the three companion tables. `python -m src.scripts.migrate_model_v1 --downgrade --schema APPROVED_SCHEMA` refuses nonempty research history by default. Archive research history first. The destructive `--allow-data-loss` override requires explicit operator approval and is never used against application data by this integration.
- Removing the ignored v1 package/runtime causes honest v1 unavailability; old saved legacy rows remain readable. Do not rewrite a model/scaler or replace an artifact with a differently hashed version to make a test pass.
- Live-data blockers remain: CHIRPS release latency and original released-at evidence, CHIRPS/EAT accumulation alignment, complete next-day-issue availability of historical ERA5-Seamless inputs, approved static-terrain provenance, and an actual ingestion adapter with tested source freshness. Current forecast weather is not a scientifically equivalent substitution.
- Observed flood/non-flood validation, calibrated flood probabilities, emergency delivery/threshold policy, independent local spatial skill and hydraulic inundation are not implemented. An alternative real-time-input model would be a separately approved research/training task. Do not infer production readiness from passing integration tests.
