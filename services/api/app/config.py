from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The API connects as a non-owner role so row-level security applies.
    database_url: str = "postgresql+psycopg://aibos_app:aibos_app@localhost:5432/aibos"
    # Migrations run as the schema owner.
    migrations_database_url: str = "postgresql+psycopg://aibos:aibos@localhost:5432/aibos"

    # "dev" trusts an X-User-Email header (local only). "clerk" verifies Clerk session JWTs.
    auth_mode: str = "dev"
    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None

    anthropic_api_key: str | None = None
    # Model tiers from the technical plan: Sonnet for agent work.
    agent_model: str = "claude-sonnet-5-5"

    storage_dir: Path = Path("./storage")
    max_upload_mb: int = 25
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
