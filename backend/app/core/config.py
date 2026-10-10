"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
_ENV_FILES = (
    (str(_PROJECT_ROOT_ENV), ".env")
    if _PROJECT_ROOT_ENV.is_file()
    else (".env",)
)


class Settings(BaseSettings):
    """Runtime settings for FoodPulse."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FoodPulse"
    environment: str = "development"
    debug: bool = True

    database_url: str

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Optional / later modules
    ml_model_dir: str = "./models"
    data_dir: str = "./data"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
