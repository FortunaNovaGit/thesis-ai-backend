from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    agent_mode: str = "mock"
    openai_model: str = "gpt-5.6-sol"
    openai_api_key: str | None = None

    # mock | auto | abilities_rest | bridge_rest
    wordpress_mode: str = "mock"
    wordpress_url: str | None = None
    wordpress_username: str | None = None
    wordpress_application_password: str | None = None
    wordpress_verify_ssl: bool = True
    wordpress_timeout_seconds: float = 30.0

    auto_approve_medium_risk: bool = True
    max_repair_loops: int = 2

    # Central backend prototype state. These are deployment settings, not settings
    # that WordPress end users need to configure.
    backend_data_file: str = "data/sites.json"
    backend_key_file: str = "data/backend.key"
    allow_insecure_wordpress: bool = False
    allow_private_wordpress: bool = False


settings = Settings()
