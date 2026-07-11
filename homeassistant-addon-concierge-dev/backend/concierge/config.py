"""Runtime settings, populated from CONCIERGE_* environment variables.

The add-on run script maps config.yaml options onto these variables; in dev
they are set directly. `skills` accepts a JSON list (pydantic-settings parses
complex types from JSON).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_TITLE_MODEL = "claude-haiku-4-5"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONCIERGE_")

    provider: str = "anthropic"
    model: str = "claude-sonnet-5"
    title_model: str | None = None
    api_key: str = ""
    base_url: str | None = None
    auto_run_tools: bool = False
    skills: list[str] = []
    ha_url: str = ""
    ha_token: str = ""
    data_dir: Path = Path("/data")
    # Built frontend directory; when set (and existing) the app serves it
    # with an SPA fallback. None in tests/dev keeps the API pure.
    static_dir: Path | None = None
    host: str = "0.0.0.0"
    port: int = 8098
    log_level: str = "info"
    # OTel instrumentation toggle; export target comes from the standard
    # OTEL_EXPORTER_OTLP_* env vars (Langfuse/Logfire both consume OTLP).
    tracing: bool = False

    @property
    def effective_title_model(self) -> str:
        """Explicit `title_model` wins; otherwise fall back per spec §5.1.

        The fixed `DEFAULT_TITLE_MODEL` name ("claude-haiku-4-5") is only
        valid on the Anthropic native provider. On any other provider (or
        a custom `base_url`), falling back to a Claude model name would
        build an unresolvable model string/config, so fall back to the
        chat `model` instead.
        """
        if self.title_model:
            return self.title_model
        if self.provider == "anthropic" and self.base_url is None:
            return DEFAULT_TITLE_MODEL
        return self.model


def load_settings() -> Settings:
    return Settings()
