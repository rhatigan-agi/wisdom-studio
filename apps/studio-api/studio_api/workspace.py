"""Workspace lifecycle for multi-agent (wisdom-layer 1.2.0+) features.

A single :class:`WorkspaceManager` owns one :class:`wisdom_layer.workspace.Workspace`
for the Studio install. Every agent built by :class:`SessionManager` is auto-
registered with the workspace on first session boot — Studio users do not have
to wire workspace registration manually; multi-agent capabilities (shared
memory, agent-to-agent messaging, team dreams) "just work" once an Enterprise
license is configured.

The license gate is the integration point. ``Workspace.initialize()`` raises
:class:`TierRestrictionError` when the license is missing or below Enterprise.
The manager catches that exception once, caches the failure, and returns
``available=false`` from :meth:`status` so the SPA can render a CTA instead
of every per-agent boot retrying (and surfacing) the same failure.

For now the workspace storage is SQLite-only —
``PostgresWorkspaceBackend`` is a v1.2.0 skeleton that raises
:class:`NotImplementedError` on initialize. Studio will re-evaluate when the
v1.3.0 SDK ships the Postgres runtime.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from wisdom_layer import WisdomAgent
from wisdom_layer.errors import TierRestrictionError
from wisdom_layer.workspace import (
    Workspace,
    WorkspaceSQLiteBackend,
)

from studio_api.schemas import AgentDetail
from studio_api.settings import settings

logger = logging.getLogger(__name__)


_WORKSPACE_ID = "studio-default"
_WORKSPACE_NAME = "Wisdom Studio Workspace"


@dataclass(frozen=True)
class WorkspaceUnavailable:
    """Cached failure record from ``Workspace.initialize()``.

    Carries the same structured shape the Studio HTTP layer renders for
    license-gate failures, so the SPA can branch on a single response.
    """

    reason: str  # "enterprise_required", "license_missing", "init_failed"
    feature: str | None = None
    required_tier: str | None = None
    upgrade_url: str | None = None
    message: str = ""


@dataclass
class WorkspaceManager:
    """Singleton workspace owner. Lazy-initialized on first agent bind."""

    _workspace: Workspace | None = None
    _unavailable: WorkspaceUnavailable | None = None
    _registered_agents: set[str] = field(default_factory=set)
    _init_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _initialized_at: datetime | None = None

    async def ensure_initialized(self, license_key: str | None) -> bool:
        """Initialize the workspace once. Cache the outcome (success or gate).

        Returns ``True`` if the workspace is available for use, ``False`` if
        the license gate prevents it (or any other initialize-time failure
        caused us to disable multi-agent features for this process).

        Idempotent — concurrent first-callers serialize on the lock; later
        calls return the cached state without re-trying.
        """
        if self._workspace is not None:
            return True
        if self._unavailable is not None:
            return False

        async with self._init_lock:
            if self._workspace is not None:
                return True
            if self._unavailable is not None:
                return False

            if not license_key:
                self._unavailable = WorkspaceUnavailable(
                    reason="license_missing",
                    feature="multi_agent_workspace",
                    required_tier="Enterprise",
                    message=(
                        "Multi-agent workspace requires an Enterprise license. "
                        "Set WISDOM_LAYER_LICENSE or save a license key from Studio Settings."
                    ),
                )
                logger.info("studio.workspace.license_missing")
                return False

            workspace = _build_workspace(license_key)
            try:
                await workspace.initialize()
            except TierRestrictionError as exc:
                self._unavailable = WorkspaceUnavailable(
                    reason="enterprise_required",
                    feature=exc.feature,
                    required_tier=exc.required_tier,
                    upgrade_url=exc.upgrade_url,
                    message=str(exc),
                )
                logger.info(
                    "studio.workspace.tier_restricted",
                    extra={"feature": exc.feature, "required_tier": exc.required_tier},
                )
                return False
            except Exception as exc:  # noqa: BLE001 — never crash agent boot
                self._unavailable = WorkspaceUnavailable(
                    reason="init_failed",
                    message=str(exc),
                )
                logger.exception("studio.workspace.init_failed")
                return False

            self._workspace = workspace
            self._initialized_at = datetime.now(UTC)
            logger.info(
                "studio.workspace.initialized",
                extra={"workspace_id": _WORKSPACE_ID},
            )
            return True

    async def bind_agent(self, agent: WisdomAgent, detail: AgentDetail) -> None:
        """Register an agent with the workspace, no-op if unavailable.

        Studio always tries to bind, regardless of license tier — when the
        license gate fires once, every subsequent bind short-circuits cheaply
        on the cached failure. Single-agent flow keeps working untouched.
        """
        license_key = (
            settings.wisdom_layer_license  # env fallback
        )
        # We intentionally don't peek at studio_config here — the caller
        # (sessions.get_or_create) has already resolved the layered key and
        # passed it into the agent. Bind uses the same resolution path via
        # ensure_initialized for first call; later calls use the cached state.
        if not await self.ensure_initialized(license_key):
            return
        if detail.agent_id in self._registered_agents:
            return
        assert self._workspace is not None  # ensure_initialized=True invariant
        capabilities = self._derive_capabilities(detail)
        try:
            await self._workspace.register_agent(agent, capabilities=capabilities)
        except Exception:  # noqa: BLE001 — never crash agent boot on a workspace bug
            logger.exception(
                "studio.workspace.register_failed",
                extra={"agent_id": detail.agent_id},
            )
            return
        self._registered_agents.add(detail.agent_id)
        logger.info(
            "studio.workspace.agent_registered",
            extra={"agent_id": detail.agent_id, "capabilities": capabilities},
        )

    async def status(self, license_key: str | None) -> dict[str, Any]:
        """Public status used by ``GET /api/workspace/status``.

        Triggers initialization if it hasn't been attempted yet so a fresh
        SPA load sees the real availability without needing to first create
        an agent.
        """
        await self.ensure_initialized(license_key)
        if self._workspace is None:
            unavail = self._unavailable or WorkspaceUnavailable(reason="init_failed")
            return {
                "available": False,
                "reason": unavail.reason,
                "feature": unavail.feature,
                "required_tier": unavail.required_tier,
                "upgrade_url": unavail.upgrade_url,
                "message": unavail.message,
            }
        return {
            "available": True,
            "workspace_id": _WORKSPACE_ID,
            "name": _WORKSPACE_NAME,
            "agent_count": len(self._registered_agents),
            "initialized_at": (self._initialized_at.isoformat() if self._initialized_at else None),
        }

    async def list_agents(self) -> list[dict[str, Any]]:
        """Return the workspace agent directory.

        Empty list when the workspace is unavailable — callers can render an
        empty state without branching on availability.
        """
        if self._workspace is None:
            return []
        records = await self._workspace.directory.list(include_archived=False)
        return [
            {
                "agent_id": r.agent_id,
                "capabilities": list(r.capabilities),
                "registered_at": r.registered_at.isoformat(),
                "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
                "past_success_rate": r.past_success_rate,
            }
            for r in records
        ]

    @property
    def workspace(self) -> Workspace | None:
        """Direct accessor for routes that need the live :class:`Workspace`.

        Returns ``None`` when the license gate fired — callers should branch
        and return a 403 with the cached unavailable reason.
        """
        return self._workspace

    @property
    def unavailable_reason(self) -> WorkspaceUnavailable | None:
        return self._unavailable

    async def close(self) -> None:
        """Tear down the workspace. Called from the FastAPI lifespan shutdown."""
        if self._workspace is None:
            return
        try:
            await self._workspace.close()
        except Exception:  # noqa: BLE001
            logger.exception("studio.workspace.close_failed")
        finally:
            self._workspace = None
            self._registered_agents.clear()

    async def reset(self) -> None:
        """Test-only reset — drop cached state so the next call re-initializes.

        Production never resets a workspace mid-process; tests need this so
        each test case can install fresh fakes / different license states.
        """
        await self.close()
        self._unavailable = None
        self._initialized_at = None

    @staticmethod
    def _derive_capabilities(detail: AgentDetail) -> list[str]:
        """Map an agent's archetype to a capability list for the directory.

        Every agent gets ``"general"`` so a broadcast to "general" reaches
        the whole workspace; the archetype is added as a finer-grained
        capability that callers can target with
        :meth:`AgentDirectory.list(capability=...)`.
        """
        return ["general", detail.archetype]


def _build_workspace(license_key: str) -> Workspace:
    """Construct (but do not initialize) the workspace.

    Module-level so tests can monkeypatch ``Workspace`` and
    ``WorkspaceSQLiteBackend`` in one place.
    """
    backend = WorkspaceSQLiteBackend(path=settings.data_dir / "workspace.db")
    return Workspace(
        workspace_id=_WORKSPACE_ID,
        name=_WORKSPACE_NAME,
        api_key=license_key,
        backend=backend,
    )


workspace_manager = WorkspaceManager()


__all__ = ["WorkspaceManager", "WorkspaceUnavailable", "workspace_manager"]
