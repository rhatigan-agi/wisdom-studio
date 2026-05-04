"""In-process session manager.

One :class:`AgentSession` per ``agent_id`` holds the live :class:`WisdomAgent`,
its SDK :class:`WebSocketHub`, and a per-agent FastAPI sub-app mounted under
``/agents/{agent_id}`` on the parent Studio app. Studio is single-process /
single-user; no distributed coordination needed.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from starlette.routing import Mount
from wisdom_layer import WisdomAgent
from wisdom_layer.dashboard.ws_hub import WebSocketHub

from studio_api.cost import session_token_total
from studio_api.schemas import AgentDetail, LLMProvider, SessionState, SessionStateName
from studio_api.sdk_factory import build_agent
from studio_api.sdk_mount import build_sdk_subapp
from studio_api.settings import settings
from studio_api.store import get_agent, load_studio_config, touch_agent
from studio_api.workspace import workspace_manager

logger = logging.getLogger(__name__)

_ENV_VAR_FOR_PROVIDER: dict[LLMProvider, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "litellm": "LITELLM_API_KEY",
}


@dataclass
class AgentSession:
    detail: AgentDetail
    agent: WisdomAgent
    hub: WebSocketHub
    sub_app: FastAPI
    mount: Mount
    lock: asyncio.Lock
    # Session lifecycle (kiosk / ephemeral). The TTL clock starts on the
    # first WebSocket connect via ``mark_started`` — not on session creation
    # — so a visitor doesn't burn time during HTTP-only warmup.
    started_at: datetime | None = None
    expires_at: datetime | None = None
    tokens_used: int = 0
    state: SessionStateName = "active"
    _start_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def to_state(self) -> SessionState:
        return SessionState(
            agent_id=self.detail.agent_id,
            state=self.state,
            started_at=self.started_at,
            expires_at=self.expires_at,
            tokens_used=self.tokens_used,
            token_cap=settings.token_cap_per_session,
            session_ttl_minutes=settings.session_ttl_minutes,
        )

    async def mark_started(self) -> None:
        """Start the TTL clock on first WebSocket connect.

        Idempotent — subsequent connects (e.g. browser reconnect) keep the
        original start time so a visitor can't reset their own session by
        bouncing the WS.
        """
        if self.started_at is not None:
            return
        async with self._start_lock:
            if self.started_at is not None:
                return
            now = datetime.now(UTC)
            self.started_at = now
            if settings.session_ttl_minutes is not None:
                self.expires_at = now + timedelta(minutes=settings.session_ttl_minutes)

    async def refresh_state(self) -> SessionState:
        """Recompute token usage and TTL state from the SDK + wall clock.

        Called from the request hot path before we touch the LLM. Cheap when
        no cap is configured (skips the SDK call); when a cap is configured,
        it's a single backend aggregate query keyed by ``started_at``.
        """
        if self.state != "active":
            return self.to_state()
        if self.expires_at is not None and datetime.now(UTC) >= self.expires_at:
            self.state = "session_ended"
            return self.to_state()
        if settings.token_cap_per_session is not None and self.started_at is not None:
            self.tokens_used = await session_token_total(
                self.agent, self.started_at.isoformat()
            )
            if self.tokens_used >= settings.token_cap_per_session:
                self.state = "token_cap_reached"
        return self.to_state()


class SessionManager:
    """Manages live WisdomAgent sessions, lazily created on first request."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}
        self._creation_lock = asyncio.Lock()
        self._parent_app: FastAPI | None = None

    def attach(self, app: FastAPI) -> None:
        """Wire the parent FastAPI app so per-session sub-apps can be mounted."""
        self._parent_app = app

    async def get_or_create(self, agent_id: str) -> AgentSession:
        if existing := self._sessions.get(agent_id):
            return existing

        async with self._creation_lock:
            if existing := self._sessions.get(agent_id):
                return existing
            if self._parent_app is None:
                raise RuntimeError("SessionManager.attach(app) must be called at startup")

            detail = get_agent(agent_id)
            if detail is None:
                raise KeyError(f"agent not found: {agent_id}")

            studio_config = load_studio_config()
            provider_key = self._resolve_provider_key(
                studio_config.provider_keys, detail.llm_provider
            )
            # Persisted license wins; env is the fallback for cloud/Docker
            # deployments that never run the FirstRun wizard.
            license_key = studio_config.license_key or settings.wisdom_layer_license

            agent = build_agent(
                detail,
                provider_api_key=provider_key,
                license_key=license_key,
            )
            await agent.initialize()

            # Bind into the multi-agent workspace if one is available.
            # Silent no-op when the license tier doesn't support it — the
            # single-agent flow keeps working untouched. The workspace
            # caches its license-gate failure so this is cheap on every
            # subsequent agent boot.
            await workspace_manager.bind_agent(agent, detail)

            hub = WebSocketHub()
            hub.attach(agent)

            sub_app = build_sdk_subapp(agent)
            mount = Mount(f"/agents/{agent_id}", app=sub_app)
            self._insert_mount(mount)

            session = AgentSession(
                detail=detail,
                agent=agent,
                hub=hub,
                sub_app=sub_app,
                mount=mount,
                lock=asyncio.Lock(),
            )
            self._sessions[agent_id] = session
            touch_agent(agent_id)
            logger.info("studio.session.opened", extra={"agent_id": agent_id})
            return session

    async def close(self, agent_id: str) -> None:
        session = self._sessions.pop(agent_id, None)
        if session is None:
            return
        session.hub.detach(session.agent)
        if self._parent_app is not None:
            try:
                self._parent_app.router.routes.remove(session.mount)
            except ValueError:
                logger.warning(
                    "studio.session.mount_not_found",
                    extra={"agent_id": agent_id},
                )
        await session.agent.close()
        logger.info("studio.session.closed", extra={"agent_id": agent_id})

    async def close_all(self) -> None:
        for agent_id in list(self._sessions.keys()):
            await self.close(agent_id)

    def _insert_mount(self, mount: Mount) -> None:
        """Insert a per-agent mount, preserving precedence over the SPA fallback.

        In production the parent app registers a catch-all `/{path:path}` route
        (the SPA fallback). Routes are matched in order, so a mount appended
        after the catch-all would never be reached. When the fallback exists,
        we insert the mount immediately before it; otherwise we append.
        """
        assert self._parent_app is not None  # checked by caller
        routes = self._parent_app.router.routes
        fallback = getattr(self._parent_app.state, "spa_fallback_route", None)
        if fallback is None:
            routes.append(mount)
            return
        try:
            idx = routes.index(fallback)
        except ValueError:
            routes.append(mount)
        else:
            routes.insert(idx, mount)

    @staticmethod
    def _resolve_provider_key(keys: dict[LLMProvider, str], provider: LLMProvider) -> str:
        """Return the provider's API key, preferring persisted over env.

        Persisted keys come from the FirstRun wizard / Settings page (saved to
        ``studio.json``). Env keys come from ``ANTHROPIC_API_KEY`` etc. and
        are the fallback path used by Docker / Fly / cloud deploys that never
        run the wizard. Persisted wins so a self-hoster can override an env
        default through the GUI.
        """
        key = keys.get(provider, "") or settings.env_provider_keys.get(provider, "")
        if not key and provider != "ollama":
            raise RuntimeError(
                f"No API key configured for provider {provider!r}. "
                "Set it from the Studio Settings page, the matching env var "
                f"({_ENV_VAR_FOR_PROVIDER.get(provider, '<env>')}), or .env."
            )
        return key


session_manager = SessionManager()


__all__ = ["AgentSession", "SessionManager", "session_manager"]
