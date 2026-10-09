# NairobiFloodWatch — Backend API

FastAPI + PostgreSQL backend for the NairobiFloodWatch real-time urban
flash-flood prediction system (Strathmore University capstone project).

Serves flood risk predictions (XGBoost, 4 risk levels across 8 Nairobi
County zones), alert management, citizen flood reports, and user
authentication to the React dashboard in `dashboard/`.

## How to run locally

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

## Default credentials (seeded by init_db)

| Role    | Email              | Password    |
|---------|--------------------|-------------|
| admin   | admin@flood.ke     | admin123    |
| officer | officer@flood.ke   | officer123  |

## Notes

- If `models/flood_model_final.joblib` (and its scaler/feature-columns
  companions) are missing, the API still starts — `MLService` falls back
  to mock "Moderate" predictions and logs a warning.
- The hourly prediction pipeline uses county-level Open-Meteo weather data
  applied identically to all 8 zones; zone differentiation is baked into
  the model via terrain features used at training time.
