"""Application settings loaded from environment variables via pydantic-settings."""

import logging
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """All required environment variables for the backend.

    pydantic-settings reads values from the OS environment and, if present,
    a .env file in the working directory.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    debug: bool = False
    log_level: str = "INFO"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./dev.db",
        description="SQLAlchemy async URL, e.g. postgresql+asyncpg://... or sqlite+aiosqlite:///./dev.db",
    )

    # ── Microsoft Graph / Bot ─────────────────────────────────────────────────
    # Optional in local dev — required in production
    azure_tenant_id: str = Field(default="dev-tenant", description="Azure AD tenant ID")
    azure_client_id: str = Field(default="dev-client-id", description="Azure AD app client ID")
    azure_client_secret: str = Field(default="dev-client-secret", description="Azure AD app client secret")
    bot_app_id: str = Field(default="dev-local", description="Bot Framework App ID")
    bot_app_password: str = Field(default="dev-local", description="Bot Framework App Password")

    # ── Scheduler HMAC ────────────────────────────────────────────────────────
    scheduler_hmac_secret: str = Field(
        default="dev-hmac-secret-change-in-production",
        description="Shared secret for HMAC-SHA256 verification of scheduler calls",
    )

    # ── Admin Seeding ─────────────────────────────────────────────────────────
    # Stored as comma-separated string in env; parsed to list by validator
    initial_admin_user_ids_raw: str = Field(
        "",
        alias="INITIAL_ADMIN_USER_IDS",
        description="Comma-separated AAD Object IDs to seed as initial team leads",
    )

    @field_validator("initial_admin_user_ids_raw", mode="before")
    @classmethod
    def _validate_admin_ids(cls, v: str) -> str:
        return v.strip()

    @property
    def initial_admin_user_ids(self) -> list[str]:
        """Parsed list of initial admin AAD Object IDs."""
        if not self.initial_admin_user_ids_raw:
            return []
        return [
            part.strip()
            for part in self.initial_admin_user_ids_raw.split(",")
            if part.strip()
        ]

    # ── Slack Bot ────────────────────────────────────────────────────────────────
    slack_bot_token: str = Field(default="", description="Slack Bot User OAuth Token (xoxb-...)")
    slack_signing_secret: str = Field(default="", description="Slack App Signing Secret")

    # ── Slack ─────────────────────────────────────────────────────────────────
    slack_signing_secret: str = Field(default="", description="Slack app signing secret (required in prod)")
    slack_bot_token: str = Field(default="", description="Slack bot OAuth token (xoxb-...)")

    # ── Anthropic LLM ─────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="", description="Anthropic API key (required for LLM features)")
    anthropic_model: str = Field(
        "claude-sonnet-4-6",
        description="Anthropic model ID to use for report drafting",
    )

    # ── Timezone ──────────────────────────────────────────────────────────────
    app_timezone: str = Field(
        "Asia/Seoul",
        description="IANA timezone string for deadline computation",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    The cache is intentionally process-wide.  In tests, call
    ``get_settings.cache_clear()`` before patching env vars.
    """
    settings = Settings()  # type: ignore[call-arg]
    logging.basicConfig(level=settings.log_level.upper())
    return settings
