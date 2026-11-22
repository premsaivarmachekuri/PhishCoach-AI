from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_JWT_SECRET_LEN = 32
PLACEHOLDER_MARKERS = ("change-me", "changeme", "your-secret", "replace-me")


class ConfigMissingError(RuntimeError):
    """A required runtime setting or app_config row is absent or invalid."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM (Groq). Model fallbacks are configured via model_fallbacks; if all fail the error surfaces to the caller.
    groq_api_key: str = ""
    model_generate: str = "openai/gpt-oss-120b"
    model_coach: str = "openai/gpt-oss-120b"
    model_chat: str = "openai/gpt-oss-20b"
    model_guard: str = "openai/gpt-oss-20b"
    model_fallbacks: str = "llama-3.3-70b-versatile,llama-3.1-8b-instant"  # LLM-only fallback chain

    # DuckDB & Auth
    duckdb_path: str = "./data/phishcoach.duckdb"
    jwt_secret: str = ""

    # Integrations
    hr_api_url: str = "http://localhost:8001"
    sim_api_url: str = "http://localhost:8002"
    sim_webhook_secret: str = ""

    # CORS
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Optional tracing
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    langsmith_api_key: str = ""
    langsmith_project: str = "phishcoach-ai"

    @property
    def effective_jwt_secret(self) -> str:
        secret = self.jwt_secret.strip()
        if len(secret) < MIN_JWT_SECRET_LEN or any(m in secret.lower() for m in PLACEHOLDER_MARKERS):
            raise ConfigMissingError(
                f"JWT_SECRET must be a random string of at least {MIN_JWT_SECRET_LEN} characters "
                "(placeholder values are rejected)."
            )
        return secret

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_runtime_settings() -> None:
    """Fail fast at startup instead of silently degrading at request time."""
    s = get_settings()
    _ = s.effective_jwt_secret
    if not s.groq_api_key.strip():
        raise ConfigMissingError("GROQ_API_KEY is required: the app has no offline/canned content path.")
    if len(s.sim_webhook_secret.strip()) < 16:
        raise ConfigMissingError("SIM_WEBHOOK_SECRET (>=16 chars) is required to authenticate sim webhooks.")
