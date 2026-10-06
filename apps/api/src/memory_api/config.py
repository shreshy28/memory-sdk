from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMORY_", env_file=".env", extra="ignore")

    database_url: str = Field(default="postgresql+asyncpg://memory:memory@localhost:5432/memory")
    migration_revision: str = "0001_baseline"
    log_level: str = "info"


@lru_cache
def get_settings() -> ApiSettings:
    return ApiSettings()
