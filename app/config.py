from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # auto => OpenAI when OPENAI_API_KEY is present, otherwise deterministic mock.
    agent_mode: str = "auto"
    openai_api_key: str | None = None

    # v0.7 model router. OPENAI_MODEL remains as a backward-compatible fallback.
    openai_model: str = "gpt-5.6-terra"
    openai_orchestrator_model: str = "gpt-5.6-terra"
    openai_architect_model: str = "gpt-5.6-terra"
    openai_design_model: str = "gpt-5.6-terra"
    openai_builder_model: str = "gpt-5.6-luna"
    openai_quality_model: str = "gpt-5.6-luna"
    openai_repair_model: str = "gpt-5.6-sol"

    # Per-build guardrails. These are intentionally conservative for prototype
    # development; they can be raised explicitly in Render if needed.
    max_build_cost_usd: float = 0.50
    max_total_llm_tokens: int = 30_000
    max_llm_calls: int = 10
    max_repair_loops: int = 1
    enable_llm_repair_escalation: bool = True
    # Standard business sites use the deterministic Implementation Agent compiler.
    # Enable this only when testing advisory Builder LLM behavior.
    enable_builder_llm_review: bool = False

    # Legacy push settings retained only for old CLI/tests. v0.6+ WordPress Pull
    # execution means the cloud backend does not call WordPress to mutate it.
    wordpress_mode: str = "mock"
    wordpress_url: str | None = None
    wordpress_username: str | None = None
    wordpress_application_password: str | None = None
    wordpress_verify_ssl: bool = True
    wordpress_timeout_seconds: float = 45.0

    auto_approve_medium_risk: bool = True
    transient_action_retries: int = 1

    wordpress_min_request_interval_seconds: float = 2.0
    wordpress_rate_limit_retries: int = 2
    wordpress_rate_limit_base_delay_seconds: float = 180.0
    wordpress_rate_limit_max_delay_seconds: float = 300.0
    wordpress_batch_size: int = 8
    wordpress_inter_batch_delay_seconds: float = 3.0

    # Stable secret for self-contained encrypted WordPress connection tokens.
    backend_token_secret: str | None = None
    backend_key_file: str = "data/backend.key"

    allow_insecure_wordpress: bool = False
    allow_private_wordpress: bool = False

    @property
    def resolved_agent_mode(self) -> str:
        if self.agent_mode == "auto":
            return "openai" if self.openai_api_key else "mock"
        return self.agent_mode

    @property
    def model_router(self) -> dict[str, str]:
        return {
            "orchestrator": self.openai_orchestrator_model or self.openai_model,
            "architect": self.openai_architect_model or self.openai_model,
            "design": self.openai_design_model or self.openai_model,
            "builder": self.openai_builder_model or self.openai_model,
            "quality": self.openai_quality_model or self.openai_model,
            "repair": self.openai_repair_model or self.openai_model,
        }


settings = Settings()
if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
