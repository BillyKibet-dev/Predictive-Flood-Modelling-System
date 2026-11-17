# Manual forecast collection in shadow mode

Phase 1 adds source retrieval, local evidence and quality checks. It does not
construct v1 features, load a model, issue a risk classification, publish an API
prediction, send alerts, change database contracts or register a scheduler.

## Contract and separation

`src/api/services/operational_sources.py` requests one explicitly selected
`ecmwf_ifs` initialization from Open-Meteo's Single Runs API. A manual invocation
makes at most one HTTP request for all eight existing zone IDs. There are no
automatic retries, redirects, best-match selection, cross-run merges or fallback
providers/depths. Network access requires `--fetch`.

The five hourly variables are `temperature_2m`, `relative_humidity_2m`,
`precipitation`, `wind_speed_10m` and `soil_moisture_0_to_7cm`, with explicit
Celsius, percent, mm, km/h and m3/m3 units. These are model forecasts.
The legacy weather/SCS pipeline and historical v1 replay remain separate.
[IFS variable documentation](https://open-meteo.com/en/docs/ecmwf-api)

The candidate clock is 06:00 Africa/Nairobi on date `I`, targeting the physical
Nairobi day `I+1`. Instantaneous fields require labels 00:00..23:00. Rainfall
amounts cover the preceding hour, so the physical target requires labels
01:00..the following 00:00. No rainfall aggregate or model feature is produced
in this phase. Intervals, values, nulls and true zeros are retained separately.
[Hourly definitions](https://open-meteo.com/en/docs#hourly-parameter-definition)

## Manual commands

Run from the repository root with the existing Python environment installed:

```powershell
.venv/Scripts/python.exe -m src.scripts.collect_operational_sources --help
```

The following are the two actual experimental invocations from 8 November 2026.
For a new prospective collection, explicitly choose the run and candidate issue
date for that experiment; running an old issue now will correctly be late.

```powershell
.venv/Scripts/python.exe -m src.scripts.collect_operational_sources --fetch --run 2026-11-07T12:00:00Z --issue-date 2026-11-08
.venv/Scripts/python.exe -m src.scripts.collect_operational_sources --fetch --run 2026-11-07T18:00:00Z --issue-date 2026-11-08
```

By default the command reads only `id`, `latitude`, `longitude` from
`public.zones` in an explicitly read-only transaction. It does not initialize
tables or query users. An explicit `--zones-file path/to/zones.json` can replace
that lookup; it must contain exactly the eight supported IDs and coordinates.
The portable public test catalogue is `tests/fixtures/operational_sources/zones.json`.
There is no implicit fallback to it if the database is unavailable.

Use `--store-root` to select a dedicated evidence directory. The default is
`data/operational_sources/`, which is ignored by Git. Model directories,
historical training data and audit captures are protected output locations.
Optional `--output new-report.json` creates a new report copy and refuses to
overwrite an existing file. Without it, the immutable report path is printed.

Exit 0 means the complete target windows and original receipt/storage timing
passed the **shadow source** gate. Exit 2 means not ready, with a saved report
for provider/coverage/quality/timing failure. Exit 1 is a configuration, storage
or integrity failure. No exit code authorizes inference or establishes daily
reliability. Do not parse a source PARTIAL status as a Low risk classification.

## Evidence layout and offline replay

The local store uses SHA-256 object names for:

- `raw/sha256/<prefix>/<hash>.bin`: original transport-decoded response bytes,
  without JSON reserialization; partial bodies are explicitly marked incomplete.
- `captures/sha256/<prefix>/<hash>.json`: request/receipt times, request
  parameters, zone catalogue, safe HTTP headers, raw reference, storage time and
  attribution. Failed requests retain their attempt metadata, with no invented
  raw body/hash when no response was received.
- `readiness/sha256/<prefix>/<hash>.json`: per-zone grid/elevation, units,
  original valid times, physical precipitation intervals, missing/invalid
  values, run identity basis, target coverage and timing/readiness results.

The writer publishes complete fsynced objects without clobbering existing hash
paths. Reuse verifies existing bytes. References are confined to the store;
replay verifies hashes and lengths. This is an append-only local writer with
tamper detection, not signed provider publication evidence. Host-clock accuracy
and filesystem retention remain deployment responsibilities for a later phase.

Offline replay uses saved policy, coordinates and original receipt/storage
timestamps. It makes no database query or external request, and accepts no
issue-date, run or age-limit override. Replaying after 06:00 does not turn the
new replay time into the old source availability time.

```powershell
$fixtureIndex = Get-Content tests/fixtures/operational_sources/index.json -Raw | ConvertFrom-Json
$fixtureReport = Join-Path tests/fixtures/operational_sources $fixtureIndex.available_12utc.path
.venv/Scripts/python.exe -m src.scripts.collect_operational_sources --replay $fixtureReport --store-root tests/fixtures/operational_sources
```

The curated success and provider-error fixtures include public weather data and
public study coordinates only. Their README preserves licence, attribution,
actual capture context and immutable references. Tests do not depend on the
locally ignored original audit directory. Local implementation reports and
readiness results remain excluded through `.git/info/exclude`; this runbook and
the fixture specifications preserve portable reproduction instructions.

## Quality and readiness interpretation

QC requires eight identities; exact request model/run/variables; returned grids;
correct units/timezone; 72 unique ordered hourly labels; full required target
intervals; finite, plausible required values; consistent initialization; and
eligible original receipt/storage times. No missing value becomes zero and no
other soil layer is accepted. A broad 0.5-degree grid-distance check detects
misassociated locations; it is not a measure of flood prediction accuracy.

Missing values outside the required target are retained and make source quality
PARTIAL. They do not invalidate an otherwise complete target. Missing required
values, unit/depth changes, incomplete coverage, late receipts and source errors
prevent snapshot readiness. `cutoff_evidence` describes response receipt/storage
timing; it must be read with `target_window_quality` and `snapshot_readiness`.
An early HTTP error response is not evidence of available weather data.

The default 18-hour run-age guard is provisional research configuration, not a
validated production freshness limit. `--max-run-age-hours` can select a
different explicit research guard at collection time. Saved policy is immutable.

Original provider publication time remains null unless independently supported.
An explicit run parameter and first-valid-time alignment establish the requested
initialization, not when it became public. HTTP Date and receipt time have
different meanings. No independent cycle identifier was returned in these
captures. [Provider timing definitions](https://open-meteo.com/en/docs/model-updates)

## Demonstrated result and remaining gate

The 7 November 12:00 UTC run was received at **8 November 00:21:44.888 EAT**,
with raw/capture storage complete at **00:21:44.913 EAT**. All eight required
9 November target windows passed. Initial rainfall at 7 November 15:00 EAT was
null for each zone, outside the target; it was preserved. Source quality is
PARTIAL while target quality passes. The run is 15 hours old at the candidate
06:00 issue under the explicit provisional guard.

The 18:00 UTC run returned HTTP 400 at **00:21:56.135 EAT**, reporting it was not
available. The independent 12:00 request was not an automatic fallback. There
were exactly two live requests and no retries. This does not show that the
18:00 run would still be unavailable at 06:00, or that either cycle consistently
meets the cutoff. Repeated prospective collections are still required before
selecting an operational run policy. [Explicit run API](https://open-meteo.com/en/docs/single-runs-api)

Review Phase 1 results before persistent database snapshots, v2 dataset/training
or scheduling. Keep the selected v1 historical model and all its integrity and
live-mode blockers unchanged.

## Phase 2: persist previously captured evidence

Phase 2 adds an explicit PostgreSQL migration and an offline importer. Collection
remains a separate manual operation. Nothing in this path starts a source fetch,
model inference, daily job or frontend/API publication. Detailed table and
recovery contracts are in `docs/integration/operational_source_persistence.md`.

Apply migration 005 once to the approved existing schema. The schema must have
its own `zones` table with coordinates; there is no fallback to another schema.

```powershell
.venv/Scripts/python.exe -m src.scripts.migrate_operational_sources --schema public
$fixtureIndex = Get-Content tests/fixtures/operational_sources/index.json -Raw | ConvertFrom-Json
$savedReport = Join-Path data/operational_sources $fixtureIndex.available_12utc.path
.venv/Scripts/python.exe -m src.scripts.persist_operational_sources --readiness $savedReport --store-root data/operational_sources --dry-run
.venv/Scripts/python.exe -m src.scripts.persist_operational_sources --readiness $savedReport --store-root data/operational_sources --schema public
```

The example assumes the original Phase 1 local store is installed. For portable
fixture validation, select `tests/fixtures/operational_sources` as the store and
construct `$savedReport` relative to that root. Dry-run verifies files and
original eligibility without connecting to PostgreSQL or writing any file.
The real importer does not apply migrations automatically.

Repeat the same import safely: the collection attempt, receipt, eight QC rows
and eligible snapshot are reused; each invocation has a distinct import journal.
`IMPORTED`/`REUSED` describes persistence success. A saved provider HTTP 400 is
stored with attempt outcome `PROVIDER_FAILED` and **no snapshot**; successful
audit persistence does not turn a failed source into a forecast.

Use the returned snapshot ID to re-check both DB membership and original files:

```powershell
.venv/Scripts/python.exe -m src.scripts.persist_operational_sources --check-snapshot <snapshot-uuid> --store-root data/operational_sources --schema public
```

Ready-as-recorded eligibility is immutable. Missing/corrupt files or changed
geography make this read check report `UNAVAILABLE`; it never fabricates input
values or silently rewrites the old snapshot. Restore exact verified original
objects from an approved copy before reuse.

The original receipt/source-storage timestamps are separate from database
import/journal times. Unknown publication remains NULL. Import time is never
substituted for earlier availability. Failed imports roll back the complete
source graph. A separate journal records failure when possible; if the database
is unavailable, a local content-addressed failure report explicitly says the
database outcome is unconfirmed. Safe retries resolve uncertain outcomes.

For an interrupted/failed import, use the same evidence and optionally
`--resume-import-id <previous-import-uuid>` to link the new journal. Prior
STARTED/FAILED history is preserved rather than rewritten. A STARTED entry
alone is not proof of completion or failure.

Rollback refuses nonempty Phase 2 tables by default. Archive the six new tables
and referenced evidence first; removal with `--downgrade --allow-data-loss`
requires explicit operator authorization. It affects only Phase 2 tables and
functions and uses no CASCADE. The local implementation report and rollback
guide record actual verification; no public-schema rollback was performed.

### Regression verification

```powershell
.venv/Scripts/python.exe -m pytest tests/test_operational_sources.py -q
$env:RUN_MODEL_V1_POSTGRES_TESTS = '1'
$env:RUN_POSTGIS_TESTS = '1'
$env:RUN_ENVIRONMENTAL_POSTGRES_TESTS = '1'
$env:RUN_REPORT_POSTGRES_TESTS = '1'
$env:RUN_OPERATIONAL_SOURCE_POSTGRES_TESTS = '1'
.venv/Scripts/python.exe -m pytest tests --ignore=tests/test_proxy_evaluation.py -q
```

The opt-in native suites create and remove disposable UUID-named schemas.
Remaining tests use isolated records/SQLite/fixtures. The unrelated legacy
evaluation-diagnostic suite is excluded from this collection increment; no
evaluation/training job is launched. Frontend code is unchanged.
Exact results, commands, protected-file checks and limitations belong in the
local `SHADOW_COLLECTION_IMPLEMENTATION_REPORT.md` and
`data/operational_sources/phase1_verification/`.

Weather data by [Open-Meteo.com](https://open-meteo.com/), ECMWF IFS;
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) with attribution.
Raw responses are unchanged; diagnostic metadata were added. This bounded
academic collection uses the non-commercial API under the
[service terms](https://open-meteo.com/en/terms).
