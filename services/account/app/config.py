from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACCOUNT_")

    service_name: str = "account-service"
    host: str = "0.0.0.0"
    port: int = 8001
    database_url: str = "sqlite+aiosqlite:///./account.db"
    log_level: str = "INFO"
    otlp_endpoint: str | None = None


settings = Settings()
