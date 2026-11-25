from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every field is filled in by pydantic-settings, never in this file.

    On `Settings()`, each field is read from the environment variable with the same name
    (case-insensitive, so `db_path` <- `DB_PATH`), falling back to the `.env` file.
    A field with no value in either place raises a ValidationError naming that field.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: SecretStr
    anthropic_model: str
    db_path: Path


@lru_cache
def get_settings() -> Settings:
    return Settings()
