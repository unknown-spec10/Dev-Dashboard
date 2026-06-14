from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    POSTGRES_ASYNC_URI: str = "postgresql+asyncpg://postgres:postgres@db:5432/dev_dashboard"
    POSTGRES_SYNC_URI: str = "postgresql+psycopg2://postgres:postgres@db:5432/dev_dashboard"
    REDIS_URI: str = "redis://redis:6379/0"
    SECRET_KEY: str = "dev-dashboard-secret-key-change-me"

    model_config = SettingsConfigDict(case_sensitive=True)

settings = Settings()
