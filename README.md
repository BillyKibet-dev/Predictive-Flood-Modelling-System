# NairobiFloodWatch

Flood-risk monitoring prototype for Nairobi County, Kenya —
a Strathmore University industry capstone project.

A trained XGBoost model classifies weather-based risk into four levels (**Low,
Moderate, High, Extreme**). One shared Nairobi weather indication is displayed
against **8 monitoring locations** and summarised by sub-county. Street-level
flooding and local drainage are not assessed. Predictions, alerts, and citizen reports are served through a
FastAPI backend to a React dashboard used by three kinds of users:

- **Citizens** — view current risk per zone and submit flood condition reports, no login required
- **Authorities (officers)** — monitor the live risk map, manage and acknowledge alerts
- **System administrators** — manage user accounts, alert thresholds, and review model performance

## Architecture

```mermaid
flowchart LR
    W["Open-Meteo API<br/>(weather data)"] --> P["Prediction Pipeline<br/>(hourly, APScheduler)"]
    P --> M["XGBoost Model<br/>(src/api/services/ml_service.py)"]
    M --> DB[("PostgreSQL<br/>zones, predictions, alerts, users, reports")]
    DB --> API["FastAPI Backend<br/>src/api/"]
    API <--> UI["React Dashboard<br/>dashboard/"]
```

## Repository structure

```
Predictive-Flood-Modelling-System/
├── dashboard/        React + Vite frontend (citizen, officer, and admin views)
├── src/
│   ├── api/          FastAPI backend (routers, services, models, utils)
│   └── scripts/      init_db.py, run_pipeline.py
├── models/           Trained XGBoost model + scaler + feature columns (.joblib)
├── data/             Raw/processed data used for model training
├── notebooks/        Model training & evaluation notebook (FloodHub.ipynb)
├── tests/            Backend API smoke tests (pytest)
├── requirements.txt  Backend Python dependencies
└── .env.example      Backend environment variable template
```

## Quick start

Two independent apps make up the system — run them side by side during development.

### 1. Backend (FastAPI + PostgreSQL)

Install dependencies:

```
pip install -r requirements.txt
```

Set up PostgreSQL:

```
createdb nairobifloodwatch
```

or via `psql`:

```sql
CREATE DATABASE nairobifloodwatch;
```

Copy the environment file and edit it with your DB password and secret key:

```
cp .env.example .env
```

Generate a secret key (minimum 32 characters):

```
python -c "import secrets; print(secrets.token_hex(32))"
```

Initialise the database and seed zones/users/initial predictions:

```
python -m src.scripts.init_db
```

Start the API server:

```
uvicorn src.api.main:app --reload --port 8000
```

Access the API docs:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Run tests (requires the seeded database above):

```
pytest tests/ -v
```

Run the prediction pipeline manually:

```
python -m src.scripts.run_pipeline
```

To use your own trained model, drop these three files into `models/` (see
`MODEL_PATH`/`SCALER_PATH`/`FEATURE_COLS_PATH` in `.env` if you rename them),
then restart the server:

```
models/flood_model_final.joblib
models/scaler_final.joblib
models/feature_cols_final.joblib
```

### 2. Frontend (React dashboard)

```
cd dashboard
npm install
npm start
```

The dashboard runs at http://localhost:5173 with routes `/` (public map),
`/citizen`, `/login`, `/officer`, `/officer/alerts`, and `/admin`.

### Prediction refresh (issue #9)

The map, citizen risk cards, and officer risk table share one live `GET /dashboard`
subscription. Keep the backend running alongside Vite. To change the API origin or
refresh timing, copy `dashboard/.env.example` to `dashboard/.env.local` and restart
Vite (or rebuild for deployment).

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend origin; allow the frontend origin via backend `FRONTEND_URL` |
| `VITE_PREDICTION_POLL_INTERVAL_MS` | `60000` | Delay between completed prediction requests |
| `VITE_PREDICTION_STALE_AFTER_MS` | `3900000` | Mark predictions older than 65 minutes as stale |

Predictions are fetched immediately on page load, then every minute after the
previous request settles. This checks saved results from the hourly backend
pipeline; it never triggers inference. Manual refresh, returning to the tab, and
regaining connectivity also check for updates. Requests time out after 15 seconds;
requests do not overlap, and unmounting cancels requests and timers.

Failed refreshes retain the last successful snapshot with a visible warning.
Each zone displays its actual prediction timestamp in Africa/Nairobi time. Zones
without predictions show **Unknown**, and empty results do not imply low risk.
The API does not supply rainfall totals, so those fields show **Unavailable**.

Only prediction data and the summary alert count are connected in this issue.
Authentication, alert actions, user management, and model/system panels still use
the existing demo implementation and require separate integration work. Citizen
report submission is connected as described below.

Run the polling/response regression tests and production build from `dashboard/`:

```text
npm test
npm run build
```

### Public citizen warnings and reports (issue #25)

At `/citizen`, residents can filter the live warning cards by zone and select
**Report conditions** on a card to preselect that zone in the reporting form.
Warnings with old prediction timestamps are labelled as saved warnings.

The form submits anonymously to `POST /citizen-report`, using zone IDs from the
dashboard API. Supported conditions are Street flooding, River overflow, Blocked
drainage, and Other; severities are Mild, Serious, and Dangerous. Descriptions are
optional, limited to 200 characters, trimmed, and stored as null when blank.
The frontend validates entries, and the backend enforces the same values and
length limits. Zone IDs must exist in the database; the form offers no unsupported
"Other" zone.

While submitting, the form blocks repeated submissions. Success appears only
after HTTP 201 confirms the saved report ID and timestamp. Failures preserve the
entered details and show a retry message or field errors. Requests time out after
15 seconds and are cancelled when navigating away. Submissions are never retried
automatically because a lost response can follow a successful save. Reports do
not directly change model predictions or displayed risk levels.

Reports persist in `citizen_reports` and are available through the existing
admin-only `GET /citizen-reports` endpoint. The admin dashboard's report list still
uses demo data pending authentication/admin API integration.

Run the frontend tests/build above and the isolated report API tests from the
project root (with the normal backend environment configured):

```text
python -m pytest tests/test_reports.py -v
```

These report tests use an in-memory SQLite database and do not write to the
configured PostgreSQL database or start the prediction scheduler.

### Nairobi administrative boundary (issue #16)

With the backend environment configured, load the committed county and 17
sub-county boundaries:

```text
python -m src.scripts.load_boundaries
```

The command enables the PostGIS extension and applies
`src/api/migrations/001_administrative_boundaries.sql`. PostgreSQL must have
PostGIS installed, and the database user needs permission to enable it (a database
administrator can run `CREATE EXTENSION IF NOT EXISTS postgis` first). Existing
API features can start without this optional spatial setup.

The importer validates the GeoJSON, stores a valid non-empty MultiPolygon with
SRID 4326 and a GiST index, and retains source/licence/year metadata. Repeat runs
update the same 18 boundary IDs; the entire import is transactional. To use another
file with the same feature/property contract, pass `--path path/to/file.geojson`.

Public GeoJSON endpoints:

- `GET /boundaries` — administrative FeatureCollection.
- `GET /boundaries/nairobi-county` — the county Feature.

Unknown boundary IDs return 404; unavailable spatial setup returns 503. The data
uses provider-simplified **2020 administrative boundaries**. Each sub-county
includes `monitoring_zone_ids`, calculated from monitoring coordinates with
PostGIS `ST_Covers`, rather than matching neighbourhood names. See
[data/README.md](data/README.md) for provenance and attribution.

### Sub-county risk map (issue #4)

The public map fetches `/boundaries` on entry and draws the county outline and
17 sub-county polygons. Colours follow the highest available prediction among
monitoring points inside each polygon and update with the existing prediction
polling. Areas without a point or an available prediction show **Unknown**.
Dashed outlines and popup messages identify old predictions; partial coverage
is stated in the popup. This aggregation describes monitored risk within an
administrative area; it does not estimate flood extent across the polygon.

Popups show contributing monitoring points, model scores, update times, source
year, and licence. **Sub-county risk** and **Monitoring points** toggle the two
layers; **Fit county** restores the county view. Prediction refreshes preserve
the current map position. Boundaries load independently of predictions: a failed
initial request leaves monitoring points available with a retry button, and a
failed reload retains the previous outlines. Boundary requests time out after
15 seconds and are cancelled on navigation. Attribution stays visible below
the map controls, including on mobile.

Run boundary validation/API tests plus existing report tests:

```text
python -m pytest tests/test_boundaries.py tests/test_reports.py -v
```

After importing, enable native PostGIS tests in PowerShell:

```powershell
$env:RUN_POSTGIS_TESTS = "1"
python -m pytest tests/test_boundaries.py tests/test_reports.py -v
Remove-Item Env:RUN_POSTGIS_TESTS
```

Spatial tests use and remove a UUID-named temporary schema. They leave application
tables intact. Set `POSTGIS_TEST_DATABASE_URL` to use a separate test database;
otherwise the configured database is used. The connection needs CREATE SCHEMA
permission and an already enabled PostGIS extension.


## Model input audit (issue #19, first step)

See [docs/model-input-audit.md](docs/model-input-audit.md) for the exact feature
contract, proxy labels, training/serving mismatches, conflicting saved metrics
and the staged plan for local flood evidence and validation. Reproduce the
artefact inspection without network/database access:

```text
python -m src.scripts.audit_model
python -m pytest tests/test_model_inputs.py tests/test_prediction_pipeline.py tests/test_model_audit.py -v
```

The live pipeline requires complete recent weather and compatible model files.
Failed runs preserve prior data and create no new predictions/alerts. The
dashboard's `prediction_context` declares shared Nairobi coverage, same-day
proxy labels and uncalibrated class scores. Missing predictions return Unknown
with null timestamps. A missing/invalid model evaluation report returns 503
instead of hard-coded performance values. The audit's structural checks do not
establish street-level accuracy or resolve the documented daily/hourly mismatch.

## Notes

- If the model/scaler/feature files are missing or their input contract does not
  match, the API still starts and reports the model as unavailable. The pipeline
  does not save placeholder predictions.
- The final nine model inputs exclude location, terrain and drainage features.
  All zones share the same weather indication; administrative polygons do not
  increase model resolution.
- Original training data and a compatible re-export are needed to reproduce
  evaluation. Saved notebook metrics describe proxy-label classification, not
  validated street flooding probabilities.
