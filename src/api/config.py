"""Application settings loaded from environment variables (.env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    MODEL_PATH: str = "models/flood_model_final.joblib"
    SCALER_PATH: str = "models/scaler_final.joblib"
    FEATURE_COLS_PATH: str = "models/feature_cols_final.joblib"

    OPEN_METEO_BASE_URL: str = "https://archive-api.open-meteo.com/v1/archive"
    OPEN_METEO_FORECAST_URL: str = "https://api.open-meteo.com/v1/forecast"
    NAIROBI_LAT: float = -1.286389
    NAIROBI_LON: float = 36.817223

    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
