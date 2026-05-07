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

import atexit
import contextlib
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import get_args

import bleach
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from studio_api.schemas import LLMProvider, LockedLLM

logger = logging.getLogger(__name__)

# Banner HTML is rendered with `dangerouslySetInnerHTML`. We accept only the
# inline-formatting tags that make sense in a one-line announcement bar; any
# script, iframe, style, or event handler is stripped.
_BANNER_ALLOWED_TAGS: tuple[str, ...] = ("a", "strong", "em", "b", "i", "br", "span")
_BANNER_ALLOWED_ATTRS: dict[str, list[str]] = {
    "a": ["href", "title", "rel", "target"],
    "span": ["class"],
}


# Anchor for repo-root-relative paths (.env, default examples/, seed_path).
# Two layouts must work:
#   * Host dev: studio_api/settings.py is at apps/studio-api/studio_api/ — the
#     repo root is four levels up.
#   * Docker:   the package is flattened to /app/studio_api/ and `examples/`
#     is copied to /app/examples — the anchor is /app, only two levels up.
# Walking up looking for an `examples/` dir handles both without hardcoding
# either depth. Falling back to the file's parent if neither layout matches
# keeps surprise out of forks that restructure the tree (.env will simply not
# load — pydantic silently skips missing files).
def _find_anchor() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "examples").is_dir():
            return candidate
    return here.parent


_REPO_ROOT = _find_anchor()

# Test escape hatch: setting STUDIO_DISABLE_DOTENV=1 skips dotenv loading so a
# developer's repo-root .env (full of demo-deployment overrides) doesn't leak
# into the test run. The conftest sets it autouse; production never sets it.
_DOTENV_FILES: tuple[Path | str, ...] = (
    () if os.environ.get("STUDIO_DISABLE_DOTENV") else (_REPO_ROOT / ".env", ".env")
)


class StudioSettings(BaseSettings):
    """Process-level configuration. Per-agent settings live in the registry."""

    model_config = SettingsConfigDict(
        env_prefix="WISDOM_STUDIO_",
        # Repo-root .env first, then cwd .env (later files override earlier).
        env_file=_DOTENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Process plumbing ----------------------------------------------------
    data_dir: Path = Field(default=Path(".wisdom-studio"))
    examples_dir: Path = Field(
        default_factory=lambda: _REPO_ROOT / "examples",
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
    # input. Unset by default so the public source ships without a hardcoded
    # commercial CTA; deployments wire it via env. Empty string is treated the
    # same as unset (suppresses the link).
    signup_url: str | None = Field(default=None)

    # --- Ephemeral / try-it-now deployment posture ---------------------------
    #
    # Ephemeral mode shapes a single-visitor demo box: studio.json is never
    # written, FirstRun is skipped (env keys must be set), and the SPA hides
    # Settings + any agent-CRUD affordances. When the operator did not set
    # ``WISDOM_STUDIO_DATA_DIR`` explicitly, ``data_dir`` is also rewritten to
    # a per-process tmp directory (``tempfile.mkdtemp``) so the SDK SQLite is
    # isolated by construction even if a forker mounts a shared volume across
    # containers in less-segregated orchestrators (Docker bind mounts, k8s
    # ReadWriteMany PVCs). An atexit handler removes that tmp directory on
    # clean shutdown — operators of long-lived containers that get restarted
    # in place should still treat ephemeral instances as disposable. An
    # explicit ``WISDOM_STUDIO_DATA_DIR`` is always respected — operators
    # opting into a known shared path are trusted to know what they're doing.
    # Combine with ``session_ttl_minutes`` and/or ``token_cap_per_session`` to
    # bound a session.
    ephemeral: bool = Field(default=False)
    # Hard cap on total LLM tokens (input + output) per session before the
    # backend returns 410 and the SPA renders the session-ended view. Counts
    # all SDK-driven calls — chat turns, dreams, critic, directives — via the
    # shared cost wrapper.
    token_cap_per_session: int | None = Field(default=None, ge=1)
    # Optional CTA shown on the session-ended / cap-reached view. Forks set
    # `session_end_cta_href` to a signup or marketing URL and override the
    # button label. Empty string suppresses the CTA entirely (same convention
    # as `signup_url`).
    session_end_cta_href: str | None = Field(default=None)
    session_end_cta_label: str | None = Field(default=None)

    # --- Auth seam (forker-tunable; default is single-user/local) ------------
    #
    # Studio's documented posture is single-user/local. The auth seam in
    # ``studio_api.auth.get_current_user`` defaults to ``User(id="local")``
    # for every request. Forks deploying behind an auth proxy can either
    # override the dependency entirely (canonical FastAPI pattern) or set
    # ``trust_user_header`` so the proxy-populated header is honored.
    #
    # The CIDR allowlist is the safety belt — without it, anyone who can
    # reach the bind port can spoof the header and become any user. When
    # ``trust_user_header`` is set and ``trusted_proxy_cidrs`` is unset, the
    # default is loopback-only (``127.0.0.0/8`` + ``::1/128``) — same-host
    # proxy is the most common shape (Caddy / nginx in front of the app).
    # Operators with a separate proxy host MUST set the CIDR explicitly.
    trust_user_header: str | None = Field(default=None)
    trusted_proxy_cidrs: str | None = Field(default=None)

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

    @model_validator(mode="after")
    def _ephemeral_isolates_data_dir(self) -> StudioSettings:
        """Swap ``data_dir`` to a per-process tmp directory in ephemeral mode.

        Fires only when the operator did NOT set ``WISDOM_STUDIO_DATA_DIR``
        explicitly — an explicit path is always honored, on the assumption
        that the operator who set it knows it's safe (or unsafe) for their
        orchestration model.

        The tmp directory is registered for cleanup via ``atexit`` so a
        graceful shutdown doesn't leave it on disk. Long-lived containers
        that get restarted in place will accumulate one entry per restart —
        operators of those should treat ephemeral instances as disposable
        (spawn fresh, don't restart).
        """
        if not self.ephemeral:
            return self
        explicit = os.environ.get("WISDOM_STUDIO_DATA_DIR", "").strip()
        if explicit:
            return self
        tmp_dir = Path(tempfile.mkdtemp(prefix="wisdom-studio-ephemeral-"))
        # Pydantic v2 lets us mutate post-validation. The override propagates
        # through the ``agents_dir`` / ``config_path`` properties below.
        object.__setattr__(self, "data_dir", tmp_dir)
        atexit.register(_cleanup_ephemeral_dir, tmp_dir)
        logger.info(
            "studio.settings.ephemeral_data_dir",
            extra={"data_dir": str(tmp_dir)},
        )
        return self

    @field_validator("signup_url", "docs_url", "session_end_cta_href", "session_end_cta_label")
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
    def seed_path_resolved(self) -> Path | None:
        """Resolve ``seed_path`` to an absolute path.

        A relative value is resolved against the repo root (which is also the
        Docker WORKDIR ``/app``) so the same env value — e.g.
        ``examples/seeds/researcher.json`` — works in both ``make dev`` and the
        container. Absolute paths are returned untouched.
        """
        if self.seed_path is None:
            return None
        if self.seed_path.is_absolute():
            return self.seed_path
        return _REPO_ROOT / self.seed_path

    @property
    def trusted_proxy_cidrs_list(self) -> tuple[str, ...]:
        """Parse ``WISDOM_STUDIO_TRUSTED_PROXY_CIDRS`` into a tuple.

        Comma-separated list (friendlier than the JSON-encoded list pydantic
        would otherwise demand). When the env var is unset:

        * Returns ``("127.0.0.0/8", "::1/128")`` if ``trust_user_header`` is
          set — same-host proxy is the most common deployment.
        * Returns ``()`` otherwise — header trust is off, no allowlist
          needed.
        """
        if self.trusted_proxy_cidrs is None:
            if self.trust_user_header:
                return ("127.0.0.0/8", "::1/128")
            return ()
        return tuple(p.strip() for p in self.trusted_proxy_cidrs.split(",") if p.strip())

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


def _cleanup_ephemeral_dir(path: Path) -> None:
    """Best-effort removal of the tmp data dir registered at boot.

    Failures are silent — atexit handlers run during interpreter teardown
    where logging may already be torn down, and a stale tmp dir is harmless
    compared to a noisy traceback at exit.
    """
    with contextlib.suppress(Exception):
        shutil.rmtree(path, ignore_errors=True)


settings = StudioSettings()
