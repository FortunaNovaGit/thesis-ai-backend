from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # auto => OpenAI when OPENAI_API_KEY is present, otherwise deterministic mock.
    agent_mode: str = "auto"
    openai_model: str = "gpt-5.6-terra"
    openai_api_key: str | None = None

    # mock | auto | abilities_rest | bridge_rest
    wordpress_mode: str = "mock"
    wordpress_url: str | None = None
    wordpress_username: str | None = None
    wordpress_application_password: str | None = None
    wordpress_verify_ssl: bool = True
    wordpress_timeout_seconds: float = 45.0

    auto_approve_medium_risk: bool = True
    max_repair_loops: int = 2
    transient_action_retries: int = 1

    # Stable secret for self-contained encrypted WordPress connection tokens.
    # Configure once in Render. Redeploys then do not invalidate connected sites.
    backend_token_secret: str | None = None
    backend_key_file: str = "data/backend.key"

    allow_insecure_wordpress: bool = False
    allow_private_wordpress: bool = False

    @property
    def resolved_agent_mode(self) -> str:
        if self.agent_mode == "auto":
            return "openai" if self.openai_api_key else "mock"
        return self.agent_mode


settings = Settings()
if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
    # Make .env-based local configuration visible to the OpenAI Agents SDK too.
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
