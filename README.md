# NairobiFloodWatch

Nairobi weather and community-report monitoring prototype, built with FastAPI,
PostgreSQL/PostGIS and React/Leaflet for a final-year capstone.

The application combines genuine forecast rainfall, mapped monitoring locations,
dated geographic context, historical satellite water mapping and citizen reports.
Its current live outlook uses **transparent rainfall thresholds**, not a validated
street-flood classifier. Environmental proxy classes, historical satellite-detected
water and predicted inundation are different things; the application supplies no
validated inundation depth/extent or calibrated flood probabilities.

**Live:** [nairobifloodwatch.me](https://nairobifloodwatch.me) (frontend, Netlify) ·
`api.nairobifloodwatch.me` (backend, Azure VM).

## Project structure

```text
.
├── src/
│   ├── api/                  FastAPI backend (entry point: src/api/main.py)
│   │   ├── routers/          HTTP endpoints: reports, routes, advisories, staff data, monitoring areas, auth
│   │   ├── services/         the logic: rainfall rule, Stage 2 model, IMERG rain, route check, live verification
│   │   ├── models/           database tables (SQLAlchemy) and request/response schemas (Pydantic)
│   │   ├── migrations/       numbered SQL migrations, applied by src/scripts/migrate_*.py, never at startup
│   │   ├── data/             committed catalogues the API serves: monitoring areas, hotspots, susceptibility
│   │   ├── utils/            passwords, JWT sign-in and role checks
│   │   └── config.py         settings read from .env
│   ├── modeling/
│   │   ├── stage2/           live rainfall-risk model: dataset, features, training, runtime
│   │   ├── v1/               frozen 20-feature v1 model (historical replay only)
│   │   └── binary_rainfall/  staff-only binary research model
│   └── scripts/              command-line jobs: database setup, migrations, weather collection, data preparation
├── dashboard/                React + Vite + Leaflet frontend
│   ├── src/pages/            one file per screen: map, report, route checker, staff pages
│   ├── src/components/       map layers, cards, charts, staff layout
│   ├── src/services/         API calls and data shaping
│   ├── src/i18n/             English and Kiswahili text
│   ├── tests/                frontend unit tests (node:test)
│   └── scripts/              headless-browser checks
├── models/                   served model files: stage2-rainfall-risk, legacy-v2, nextday-rainfall-binary-v1
├── data/                     pinned inputs: Nairobi boundaries, CHIRPS labels and evaluation, provenance
├── tests/                    backend tests (pytest)
├── docs/integration/         runbooks and model notes
├── deploy/                   systemd and nginx examples, backup and runtime-data scripts
├── notebooks/                exploratory notebooks and the CHIRPS Colab export
├── requirements*.txt         Python dependencies (main API, plus separate sets for v1, evaluation, data prep)
└── netlify.toml              Netlify build settings for the dashboard
```

Not in Git: `.env` (secrets), `data/model_v1/` and other raw source/model bundles,
which are restored separately (see [Deployment and backup](#deployment-and-backup)).

## Current application

- **Map `/`:** 36 monitored records, all located, at 34 physical pins, grouped
  under the stored administrative boundaries. Seven were located by the user on
  15 November 2026 and four that could not be found were removed.
  Pins are coloured by tomorrow's rainfall-risk category (grey when no fresh outlook).
  Selecting an area shows a short summary first; technical detail is under More details.
- **Weather `/weather-outlook`:** the same monitored-location outlook, source/run,
  next complete Nairobi target day, receipt time and expiry. A six-hour receipt
  limit, 24-hour run-age guard and target-day boundary can withhold old values.
  Low rainfall does not establish flood safety. Shared provider grids are explicit.
- **Citizens `/citizen`:** submit observations with a specific landmark/address and
  optional actual coordinates. Reports are stored in PostgreSQL; they do not
  automatically change rainfall categories or become confirmed flood events.
- **Community reports on the map:** an officer can tick **Show on the public map** when
  reviewing a report with a map pin. It then appears as a purple triangle for 24 hours
  after it was reported (`GET /community-reports/recent`): condition, severity and
  specific location, at about 100 m. Descriptions, notes and contact details are never
  public. Marking a report Resolved removes it. Every publish/withdraw is in the review
  audit. Needs `python -m src.scripts.migrate_reports` (additive migration 006).
- **Reporting by sub-county:** citizens choose one of the 17 Nairobi sub-counties (the OSM
  outlines on the map), and dropping a pin fills it in automatically (`POST /reporting-areas/locate`,
  so a pin never appears in a URL or access log). A pin outside the chosen sub-county is refused
  with a plain explanation. Older reports keep their original zone. Needs migration 007 (same
  command as above).
- **Same-day outlook (`/monitoring-areas/today`):** forecast rain in the next 3 h and 3-6 h at each
  place (light/moderate/heavy by hourly rate: <2.5, <7.6, >=7.6 mm/h) and today's category from
  the Stage 2 model run with today as the target day: newest ECMWF run where it covers the hour,
  else the collection made yesterday for today; NASA IMERG observed rain for yesterday and the five
  days before. Falls back to the rule (lower bound) when inputs are missing. The public map opens on
  Today with a Today/Tomorrow switch. Reads stored collections only; storm timing is uncertain.
- **Local flood susceptibility:** the 36 places share only 7 forecast cells, so each also gets a
  fixed-weight score (Higher / Medium / Lower) from 30 m terrain (height above the nearest mapped
  river, ground lower than its surroundings), OpenStreetMap rivers, the 1 May 2024 satellite water
  map, built-up cover and recorded flooding (`python -m src.scripts.prepare_susceptibility`,
  served at `/monitoring-areas/susceptibility`). Ringed pins flood more easily; staff lists rank
  by tomorrow's category, then susceptibility. A ranking, not a validated probability.
- **Report tracking, photos and advisories (migrations 008, 009):** each new report returns one
  reference such as `FW-K7Q2M9` (only its hash is stored; shown once). The report page remembers
  it in the resident's browser and shows its status, so nothing has to be typed; a reference from
  another phone can be entered (`POST /citizen-report/status` with `{"reference": "FW-…"}`,
  30 checks per 10 minutes per client). Older reports still check with number + 8-character code.
  One photo per report within 2 hours, re-encoded with Pillow so
  no GPS/camera metadata survives, stored in `REPORT_PHOTO_DIR` and visible to staff only.
  Officers post time-limited advisories for a sub-county (`/advisories`), shown on the public map
  without staff names.
- **Route checker (`/route`):** OpenRouteService routing and place search through the API
  (`OPENROUTESERVICE_API_KEY`, server-side only, rate-limited). Lists checked reports, advisories,
  river crossings and flood-prone places along the route and can re-route around reported
  flooding. Never states a route is safe; start and end are not stored or logged.
- **Kiswahili:** the map, report form and route checker switch between English and Kiswahili
  (`dashboard/src/i18n/strings.js`; a test keeps both languages in step). Have a native speaker
  review the Kiswahili before launch.
- **Original model files:** the API reads `models/legacy-v2/` (XGBoost JSON + scaler numbers,
  converted by `python -m src.scripts.export_legacy_model` with identical outputs) instead of the
  version-mismatched pickles.
- **Staff workspace:** a grouped sidebar (Today, Data, Admin) replaces the long top menu.
  New pages: **Models** (`/admin/models`, the live model's validation against the rule, by
  season), **Rainfall history** (`/history`, CHIRPS 2016 to 2026), and **Downloads**
  (`/downloads`, CSV files of reports, tomorrow's outlook and rainfall history). Downloads are
  built on the server (`/exports/*.csv`, staff only), never include the IP hash, and neutralise
  spreadsheet formulas in citizen text.
- **Officers:** review persisted reports and notes, inspect nearby reports at a
  monitored point, and review saved advisories. Reporting forms are citizen-only.
- **Administrators:** manage real accounts, review reports and check system state.
  **System status → Collect latest weather** makes one explicit bounded source
  request. Repeated request IDs recover/reuse evidence. A lost acknowledgement is
  unconfirmed; use **Resume same attempt**, not an automatic new request. New admin
  requests have a 15-minute limit. Status refreshes never fetch provider weather.
- **Staff research `/research`:** historical v1 replay and an on-demand binary
  next-day rainfall research result are separate from the public weather outlook. Historical UNOSAT layers
  are optional, dated staff context, with cloud/coverage limitations.

**Automatic weather collection:** with `MONITORING_POINT_COLLECTION_AUTOMATED=true`
the API collects the forecast and observed satellite rain itself every hour at
minute 5 UTC (`MONITORING_POINT_COLLECTION_INTERVAL_HOURS`). It runs a catch-up after a
restart if the stored forecast is stale, uses one label per hour and a lock (so several
workers or a backup timer never double-request), and records each run on the admin
**System status** page. Collection does not generate alerts or write prediction records;
the outlook is classified when it is read. No public SMS/email emergency delivery is
active. The legacy inference scheduler stays off. The binary research model is
staff-only, runs on demand against a verified stored source, and never writes alerts.

## Model boundaries

| Component | Current use |
|---|---|
| Rainfall rule (Stage 1, explanation and fallback) | v1's label rule applied to live inputs: the higher of tomorrow's ECMWF forecast class (5/20/40 mm) and the 7-day total class (25/80/150 mm), where the 7-day total = 5 days of observed NASA IMERG Early satellite rain + forecast. Incomplete inputs give a flagged lower bound. See [rainfall_risk_rule.md](docs/integration/rainfall_risk_rule.md). Provisional environmental categories, not observed floods. |
| **Stage 2 XGBoost (live public outlook)** | Guarded XGBoost on the same live inputs (tomorrow's ECMWF forecast, rest-of-today forecast, 5 days of IMERG Early observed rain), trained on 924 real forecast runs (Mar 2024–Sep 2026) with CHIRPS v1 labels. Adopted by a pre-declared season-held-out test (High-or-above CSI 0.524 vs rule 0.394). Extreme only when the rule reaches High. The rule is shown alongside and used when inputs are incomplete. See [stage2_rainfall_risk_model.md](docs/integration/stage2_rainfall_risk_model.md). Not a flood probability. |
| XGBoost v1 | Frozen 20-feature historical replay, isolated pinned runtime. Live CHIRPS/weather source parity remains unresolved. |
| Binary rainfall research | Supplied ten-feature XGBoost binary model. It estimates an ERA5-estimated next-day rainfall threshold from forecast weather, not flooding. Scores are uncalibrated and monitored-area transfer is unvalidated. |

The new monitoring locations' dated NDVI, slope and land-cover context do not
automatically become inputs to any of these frozen models. Drain capacity,
blockage and measured imperviousness remain unavailable where not surveyed.

## Local setup

Use the repository root for backend commands. Install the backend dependencies in
a Python virtual environment and prepare a private PostgreSQL database:

```text
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

On Linux, use `.venv/bin/python` instead. Copy `.env.example` to `.env`, privately
fill `DATABASE_URL` and a strong `SECRET_KEY`, and set the frontend origin. Keep
`AUTO_CREATE_LEGACY_TABLES`, `LEGACY_SCHEDULER_ENABLED` and
the binary rainfall research endpoint staff-only. The private `.env` is never committed.

For a **new database only**, explicitly initialize the tables, original reporting
zones and first administrator:

```text
python -m src.scripts.init_db --admin-email your-address@example.org --admin-name "Administrator"
```

The command prompts privately for the password and confirmation. Noninteractive
operators can supply `FLOODWATCH_BOOTSTRAP_PASSWORD` through private environment
configuration; never put it on a command line or in Git. There are no default
passwords/officers and no initial prediction run. Repeating setup preserves the
existing administrator and password; additional accounts are created in the admin
UI. Existing installations keep their accounts: this change does not reset them.

Apply the existing additive migrations explicitly to the intended development or
staging database, after its backup; API startup does not apply them:

```text
python -m src.scripts.migrate_model_v1 --schema public
python -m src.scripts.migrate_environmental --schema public
python -m src.scripts.migrate_reports --schema public
python -m src.scripts.migrate_operational_sources --schema public
python -m src.scripts.load_boundaries
```

The boundary importer requires PostgreSQL's PostGIS extension and appropriate
permissions. The committed county and 17 sub-county outlines come from OpenStreetMap
(the basemap's source), checked for no overlaps or gaps; they are community-mapped,
not an official survey. Re-run the loader after any boundary update. Never run a downgrade on
preserved histories without a reviewed backup and rollback plan.

Start the backend and frontend separately:

```text
python -m uvicorn src.api.main:app --reload --port 8000
```

```text
cd dashboard
npm ci
npm run dev
```

The frontend defaults to `http://localhost:8000`; configure
`VITE_API_BASE_URL` before building for another host. API documentation is at
`/docs`. Sign in with the administrator you explicitly created, then add officers
through **User Accounts**. No sample authentication or user-management data is used.

## Forecast collection and source evidence

Source requests explicitly select an IFS 00/12 UTC run at least six hours old.
That release guard is not independent producer publication evidence. Request,
receipt and storage timestamps remain actual, and original publication is null
when unknown. The request-time outlook is separate from the frozen 06:00 EAT
research issue policy; a late capture cannot be backdated.

Use the admin control or the existing manual CLI:

```text
python -m src.scripts.collect_monitoring_point_weather --plan --current --all
python -m src.scripts.collect_monitoring_point_weather --collect --current --all
python -m src.scripts.verify_point_weather_store --round-trip
```

The collector caps one request at 40 points and 2 MiB retained body size, with no
redirects or automatic retries. It checks source units, complete physical-day
intervals, coordinates and missingness. Missing values never become zero rain.
Failed latest collections remain visible instead of falling back to an old
success. The CLI preserves its context/attempt labels for resumable collection.

`MONITORING_POINT_SOURCE_STORE` configures the shared API/collector/audit path;
unset uses `data/hotspots/point_weather`. Relative paths resolve from the repository.
Use an absolute durable mount on a server. The separate
`OPERATIONAL_SOURCE_STORE` contains Phase 2 source/snapshot evidence. Restore both
stores with PostgreSQL. Committed catalogues can be served without raw GIS runtime
dependencies; ignored raw source/model bundles must be restored separately.

Refreshing a page reads saved data; it does not queue a forecast. Stale or missing
sources show unavailable (grey pins). With automatic collection on, a failed run is
recorded and the next hourly run tries again; the outlook expires 6 hours after the last
successful collection. Keep the server clock synchronised (NTP). Do not enable legacy
automated inference.

## Verification

```text
python -m pytest tests/ -k "not reference_refit" -q
```

```text
cd dashboard
node --test --experimental-test-isolation=none
npm run build
```

From the repository root, `node dashboard/scripts/verifyStaffUI.mjs` checks browser
workflows using explicitly controlled auth/report/account/collection fixtures.
Historical and forecast browser scripts also use stored genuine evidence. These
are local checks, not proof of production reliability. Optional native PostgreSQL
tests use disposable schemas only; see the individual runbooks for their flags.
The reference-refit test is excluded to avoid fitting a model during normal checks.

## Deployment and backup

`deploy/examples/` contains **inert** API, reverse-proxy and collection-only systemd
examples. They are not installed by this repository. The environment template
keeps both inference schedulers disabled. The API and optional point collector
use the same service identity and durable point-store setting. Provision the
configured directories and permissions before starting a hardened service.

Before deployment: use a clean checkout plus verified private source/model
bundles, install locked Python/Node dependencies, apply the intended migrations,
configure HTTPS/CORS and private secrets, test actual login/report review and
explicit weather collection, and exercise an isolated paired restore. Verify NTP
before any approved unattended collection. Never expose old manual inference
routes just because scheduler flags are false; the proxy examples block them.

Back up the PostgreSQL custom-format dump **together with both complete source
stores**, including immutable objects, indexes, journals, current pointers and
manual-control records. Quiesce collection or use the documented lock order,
record hashes, restore into an isolated database/store pair and verify snapshots,
source hashes, account/report flows and interrupted-request recovery. A database
dump alone cannot restore source verification. No production deployment or timer
activation is performed by setup/build/test commands in this README.

See the [monitoring-area runbook](docs/integration/monitoring_areas.md),
[source persistence runbook](docs/integration/operational_source_persistence.md),
[v1 runbook](docs/integration/model_v1_runbook.md),
[binary rainfall research note](docs/integration/binary_rainfall_research.md) and
[historical UNOSAT runbook](docs/integration/historical_unosat_runbook.md)
for contracts, provenance, recovery procedures and remaining scientific limits.
