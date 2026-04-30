"""Studio runtime settings loaded from environment.

Two flavors of settings live here:

* **Process plumbing** — data dir, ports, CORS origins, static-serve dir.
  These are mostly internal; forkers tune them via environment but rarely
  read them.
* **Deployment knobs** — banner, session TTL, seed path, lock-provider,
  hide-settings, hide-agent-crud, docs URL, signup URL. These shape the
  user-facing product without code changes. Each is exposed via
  ``GET /api/config`` so the SPA can render accordingly.
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import bleach
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from studio_api.schemas import LLMProvider, LockedLLM

# Banner HTML is rendered with `dangerouslySetInnerHTML`. We accept only the
# inline-formatting tags that make sense in a one-line announcement bar; any
# script, iframe, style, or event handler is stripped.
_BANNER_ALLOWED_TAGS: tuple[str, ...] = ("a", "strong", "em", "b", "i", "br", "span")
_BANNER_ALLOWED_ATTRS: dict[str, list[str]] = {
    "a": ["href", "title", "rel", "target"],
    "span": ["class"],
}


class StudioSettings(BaseSettings):
    """Process-level configuration. Per-agent settings live in the registry."""

    model_config = SettingsConfigDict(
        env_prefix="WISDOM_STUDIO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Process plumbing ----------------------------------------------------
    data_dir: Path = Field(default=Path(".wisdom-studio"))
    examples_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[3] / "examples",
    )
    api_port: int = Field(default=8765)
    web_port: int = Field(default=5173)
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
    )
    # Production single-port image bakes the SPA at /app/static and sets
    # STUDIO_STATIC_DIR so the same uvicorn process can serve the UI. In dev
    # this is unset and Vite owns the frontend.
    static_dir: Path | None = Field(default=None, validation_alias="STUDIO_STATIC_DIR")

    # --- Deployment knobs (forker-tunable via env) ---------------------------
    banner_html: str | None = Field(default=None)
    session_ttl_minutes: int | None = Field(default=None, ge=1)
    seed_path: Path | None = Field(default=None)
    lock_provider: str | None = Field(default=None)
    hide_settings: bool = Field(default=False)
    hide_agent_crud: bool = Field(default=False)
    docs_url: str | None = Field(default=None)
    # Where the SPA points the "don't have a key?" link beside the license-key
    # input. Defaults to the public Wisdom Layer signup; forks override or set
    # empty string to suppress the CTA entirely.
    signup_url: str | None = Field(default="https://wisdomlayer.ai/signup/")

    # --- Provider credentials (env-only, never persisted) --------------------
    #
    # These honor the bare `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / etc. names
    # advertised by `docker-compose.yml`, the Dockerfile, and `.env.example`.
    # When set, they:
    #   1. Skip the FirstRun wizard (the API reports `initialized=true`).
    #   2. Are merged into the SDK adapter at agent-build time (in
    #      ``sessions._resolve_provider_key``), with persisted UI-set keys
    #      taking precedence so a self-hoster can override env via the GUI.
    #
    # They are NOT returned in ``GET /api/config`` — the response carries only
    # persisted keys, so an env-supplied secret never leaks through the
    # transport surface or into client memory.
    anthropic_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY")
    )
    openai_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("OPENAI_API_KEY")
    )
    gemini_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("GEMINI_API_KEY")
    )
    litellm_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("LITELLM_API_KEY")
    )
    wisdom_layer_license: str | None = Field(
        default=None, validation_alias=AliasChoices("WISDOM_LAYER_LICENSE")
    )

    @field_validator("signup_url", "docs_url")
    @classmethod
    def _empty_string_is_none(cls, value: str | None) -> str | None:
        """Treat ``WISDOM_STUDIO_SIGNUP_URL=`` as "hide" rather than a literal empty URL.

        Forkers shouldn't have to remove the env var to disable the link —
        setting it to an empty string is the conventional opt-out.
        """
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("banner_html")
    @classmethod
    def _sanitize_banner(cls, value: str | None) -> str | None:
        """Strip every tag/attribute we don't explicitly allow.

        bleach.clean() is the policy enforcer here — script, iframe, style,
        and on* handlers are removed even if a forker pastes them in by
        mistake. The raw env var is never trusted.
        """
        if value is None or not value.strip():
            return None
        return bleach.clean(
            value,
            tags=set(_BANNER_ALLOWED_TAGS),
            attributes=_BANNER_ALLOWED_ATTRS,
            strip=True,
        )

    @property
    def agents_dir(self) -> Path:
        return self.data_dir / "agents"

    @property
    def config_path(self) -> Path:
        return self.data_dir / "studio.json"

    @property
    def env_provider_keys(self) -> dict[LLMProvider, str]:
        """Sparse map of provider → key for env-supplied credentials.

        Empty strings are dropped so a deliberately-blank ``ANTHROPIC_API_KEY=``
        is treated as "unset" (matching the
        ``WISDOM_STUDIO_SIGNUP_URL=`` convention elsewhere). Ollama is never
        included — its adapter resolves its own URL from the SDK env.
        """
        candidates: dict[LLMProvider, str | None] = {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
            "litellm": self.litellm_api_key,
        }
        return {p: v for p, v in candidates.items() if v and v.strip()}

    @property
    def locked_llm(self) -> LockedLLM | None:
        """Parse ``WISDOM_STUDIO_LOCK_PROVIDER`` into a structured value.

        Format: ``"<provider>"`` or ``"<provider>:<model>"``. Unknown providers
        are silently dropped (logged elsewhere) — better to ignore a typo'd
        env var than to crash the boot.
        """
        if not self.lock_provider:
            return None
        provider, _, model = self.lock_provider.partition(":")
        provider = provider.strip()
        model = model.strip() or None
        if provider not in get_args(LLMProvider):
            return None
        return LockedLLM(provider=provider, model=model)  # type: ignore[arg-type]


settings = StudioSettings()
