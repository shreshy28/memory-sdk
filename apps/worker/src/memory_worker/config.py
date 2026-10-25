from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMORY_", env_file=".env", extra="ignore")

    database_url: str = Field(default="postgresql+asyncpg://memory:memory@localhost:5432/memory")
    migration_revision: str = "0003_episode_formation"
    worker_id: str = "worker-local"
    log_level: str = "info"
    provider: str = "fake"
    provider_base_url: str = "http://localhost:11434/v1"
    provider_model: str = "formation-model"
    embedding_model: str = "embedding-model"
    provider_api_key: str | None = None


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
