from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_")

    service_name: str = "event-gateway"
    host: str = "0.0.0.0"
    port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./gateway.db"
    account_service_url: str = "http://localhost:8001"
    log_level: str = "INFO"
    otlp_endpoint: str | None = None

    # Resiliency
    request_timeout_seconds: float = 5.0
    max_retries: int = 3
    circuit_fail_max: int = 5
    circuit_reset_timeout: int = 30

    # Rate limiting
    rate_limit: str = "100/minute"

    # Queue fallback
    queue_processing_enabled: bool = True
    queue_poll_interval_seconds: float = 10.0


settings = Settings()
