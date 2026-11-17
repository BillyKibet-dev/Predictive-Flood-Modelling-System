"""Application settings loaded from environment variables (.env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    LEGACY_MODEL_DIR: str = "models/legacy-v2"  # JSON export of the pickles below (API reads this)
    MODEL_PATH: str = "models/flood_model_final.joblib"
    SCALER_PATH: str = "models/scaler_final.joblib"
    FEATURE_COLS_PATH: str = "models/feature_cols_final.joblib"

    # Research v1 stays separate from the legacy nine-input serving artifacts.
    MODEL_V1_DIR: str = "models/nextday-proxy-v1"
    MODEL_V1_DATA_DIR: str = "data/model_v1"
    MODEL_V1_PYTHON: str = ".venv-model-v1/Scripts/python.exe"
    # Separate runtime keeps the supplied XGBoost 3.1.3 artifact reproducible.
    # It is a staff-only rainfall research model, never an alert or public flood model.
    BINARY_RAINFALL_MODEL_DIR: str = 'models/nextday-rainfall-binary-v1'
    BINARY_RAINFALL_PYTHON: str = '.venv-model-v1/Scripts/python.exe'
    # API startup is read-only by default. Bootstrap/migrations use explicit CLIs.
    AUTO_CREATE_LEGACY_TABLES: bool = False
    LEGACY_SCHEDULER_ENABLED: bool = False
    # Existing Phase 1/2 content-addressed store; weather API reads only.
    OPERATIONAL_SOURCE_STORE: str = 'data/operational_sources'
    # Optional dedicated durable mount; unset preserves the original local store.
    MONITORING_POINT_SOURCE_STORE: str | None = None
    # Automatic weather collection inside the API (services/automatic_point_collection.py).
    # Collects forecast + observed rain only; never runs alerts or writes predictions.
    MONITORING_POINT_COLLECTION_AUTOMATED: bool = False
    MONITORING_POINT_COLLECTION_INTERVAL_HOURS: int = 1
    # Citizen report photos (re-encoded, staff only). Keep outside the web root; back it up with the database.
    REPORT_PHOTO_DIR: str = "data/report_photos"
    # Route checker (openrouteservice.org). Server-side only; never sent to browsers.
    OPENROUTESERVICE_API_KEY: str = ""
    # Stage 1 rainfall-risk rule: observed antecedent rain from NASA IMERG Early (daily, V07).
    # Collected alongside forecast weather; credentials from these settings or ~/.netrc.
    IMERG_EARLY_ENABLED: bool = True
    IMERG_EARLY_STORE: str | None = None
    EARTHDATA_USERNAME: str | None = None
    EARTHDATA_PASSWORD: str | None = None
    # Stage 2: guarded XGBoost on Stage 1 inputs; the rule stays as fallback and explanation.
    STAGE2_MODEL_ENABLED: bool = True
    STAGE2_MODEL_DIR: str | None = None   # default models/stage2-rainfall-risk

    OPEN_METEO_BASE_URL: str = "https://archive-api.open-meteo.com/v1/archive"
    OPEN_METEO_FORECAST_URL: str = "https://api.open-meteo.com/v1/forecast"
    NAIROBI_LAT: float = -1.286389
    NAIROBI_LON: float = 36.817223

    ENVIRONMENT: str = "development"
    # One origin or several, comma-separated (e.g. the domain, www and the Netlify address).
    FRONTEND_URL: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def allowed_origins(frontend_url: str, environment: str) -> list[str]:
    """Browser origins allowed to call the API; localhost only outside production."""
    origins = [o.strip().rstrip("/") for o in frontend_url.split(",") if o.strip()]
    if environment != "production":
        origins.append("http://localhost:5173")
    return list(dict.fromkeys(origins))


settings = Settings()
