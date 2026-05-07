"""FastAPI entry point for the Wisdom Studio API.

Studio is the multi-agent control plane on top of the Wisdom Layer SDK. Its
own surface covers agent CRUD, examples, configuration, and a thin chat
endpoint that delegates to ``wisdom_layer.integration.respond_loop``. Every
other per-agent operation (memory, dreams, directives, status, …) is served
by the SDK dashboard's own routers, mounted per-session under
``/agents/{agent_id}`` by :class:`SessionManager`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from wisdom_layer.errors import TierRestrictionError
from wisdom_layer.integration import respond_loop

from studio_api import __version__
from studio_api.auth import CurrentUser
from studio_api.examples import list_examples, load_example
from studio_api.schemas import (
    AgentCreate,
    AgentDetail,
    AgentSummary,
    ChatRequest,
    ChatResponse,
    ExampleSummary,
    SessionState,
    StudioConfig,
    StudioConfigUpdate,
)
from studio_api.seeds import apply_seed, load_seed
from studio_api.sessions import session_manager
from studio_api.settings import settings
from studio_api.store import (
    create_agent,
    delete_agent,
    get_agent,
    list_agents,
    load_studio_config,
    save_studio_config,
)
from studio_api.workspace import workspace_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    session_manager.attach(app)
    logger.info(
        "studio.api.started", extra={"version": __version__, "data_dir": str(settings.data_dir)}
    )

    if settings.seed_path is not None:
        resolved = settings.seed_path_resolved
        assert resolved is not None  # guarded by the outer `is not None`
        spec = load_seed(resolved, configured=settings.seed_path)
        if spec is not None:
            try:
                await apply_seed(spec)
            except Exception as exc:  # noqa: BLE001 — never block startup on seed
                logger.warning(
                    "studio.seed.apply_failed",
                    extra={"seed_path": str(resolved), "error": str(exc)},
                )

    yield
    await session_manager.close_all()
    await workspace_manager.close()
    logger.info("studio.api.stopped")


app = FastAPI(
    title="Wisdom Studio API",
    version=__version__,
    description="Multi-agent control plane over the Wisdom Layer SDK.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Tier-restriction handler ------------------------------------------------
#
# SDK 1.1.0 raises ``TierRestrictionError`` with two distinct shapes:
#   * Feature-gate violation — the tier itself lacks the capability.
#   * Cap violation — the tier supports it but the Free-tier capacity is full.
#
# We map the first to 403 (forbidden by license) and the second to 402
# (Payment Required), mirroring HTTP semantics so generic clients can branch
# on status alone. The body always carries enough structure for the SPA to
# render the right CTA without re-parsing the message string.


@app.exception_handler(TierRestrictionError)
async def handle_tier_restriction(_request: Request, exc: TierRestrictionError) -> JSONResponse:
    if exc.cap_kind is None:
        return JSONResponse(
            status_code=403,
            content={
                "error": "feature_gated",
                "feature": exc.feature,
                "required_tier": exc.required_tier,
                "upgrade_url": exc.upgrade_url,
                "message": str(exc),
            },
        )
    return JSONResponse(
        status_code=402,
        content={
            "error": "cap_reached",
            "cap_kind": exc.cap_kind,
            "current": exc.current,
            "limit": exc.limit,
            "reset_at": exc.reset_at.isoformat() if exc.reset_at else None,
            "upgrade_url": exc.upgrade_url,
            "message": str(exc),
        },
    )


# --- Health ------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


# --- Identity seam -----------------------------------------------------------
#
# Default deployment is single-user/local — every request resolves to
# ``User(id="local")``. Forks that deploy behind auth wire up
# ``WISDOM_STUDIO_TRUST_USER_HEADER`` (header trust) or override
# ``get_current_user`` via ``app.dependency_overrides`` to swap in their own
# resolver. See ``studio_api/auth.py`` and ``FORKING.md`` for the full story.


@app.get("/api/whoami")
async def whoami(user: CurrentUser) -> dict[str, str]:
    return {"id": user.id}


# --- Studio config -----------------------------------------------------------


@app.get("/api/config", response_model=StudioConfig)
async def get_config() -> StudioConfig:
    return load_studio_config()


@app.put("/api/config", response_model=StudioConfig)
async def update_config(update: StudioConfigUpdate) -> StudioConfig:
    if settings.hide_settings:
        raise HTTPException(
            status_code=403,
            detail="Settings are read-only in this deployment.",
        )
    current = load_studio_config()
    if update.license_key is not None:
        current.license_key = update.license_key or None
    if update.provider_keys is not None:
        current.provider_keys = {**current.provider_keys, **update.provider_keys}
    current.initialized = True
    save_studio_config(current)
    return load_studio_config()


# --- Agents ------------------------------------------------------------------


@app.get("/api/agents", response_model=list[AgentSummary])
async def get_agents() -> list[AgentSummary]:
    return list_agents()


@app.post("/api/agents", response_model=AgentDetail, status_code=201)
async def post_agent(spec: AgentCreate) -> AgentDetail:
    if settings.hide_agent_crud:
        raise HTTPException(
            status_code=403,
            detail="Agent creation is disabled in this deployment.",
        )
    locked = settings.locked_llm
    if locked is not None:
        # Silently override — the wizard hides selection when locked, but we
        # still defend the API in case a forker scripts against it directly.
        spec = spec.model_copy(
            update={
                "llm_provider": locked.provider,
                "llm_model": locked.model if locked.model is not None else spec.llm_model,
            }
        )
    return create_agent(spec)


@app.get("/api/agents/{agent_id}", response_model=AgentDetail)
async def get_agent_detail(agent_id: str) -> AgentDetail:
    detail = get_agent(agent_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"agent not found: {agent_id}")
    return detail


@app.delete("/api/agents/{agent_id}", status_code=204)
async def delete_agent_endpoint(agent_id: str) -> None:
    if settings.hide_agent_crud:
        raise HTTPException(
            status_code=403,
            detail="Agent deletion is disabled in this deployment.",
        )
    await session_manager.close(agent_id)
    if not delete_agent(agent_id):
        raise HTTPException(status_code=404, detail=f"agent not found: {agent_id}")


# --- Examples ----------------------------------------------------------------


@app.get("/api/examples", response_model=list[ExampleSummary])
async def get_examples() -> list[ExampleSummary]:
    return list_examples()


@app.get("/api/examples/{slug}", response_model=AgentCreate)
async def get_example(slug: str) -> AgentCreate:
    """Return the full ``AgentCreate`` payload for a YAML example.

    The wizard uses this to prefill its form when a user clicks a template —
    the click no longer commits, only the explicit Create button does.
    """
    try:
        return load_example(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/agents/from-example/{slug}", response_model=AgentDetail, status_code=201)
async def post_agent_from_example(slug: str) -> AgentDetail:
    if settings.hide_agent_crud:
        raise HTTPException(
            status_code=403,
            detail="Agent creation is disabled in this deployment.",
        )
    try:
        spec = load_example(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    locked = settings.locked_llm
    if locked is not None:
        spec = spec.model_copy(
            update={
                "llm_provider": locked.provider,
                "llm_model": locked.model if locked.model is not None else spec.llm_model,
            }
        )
    return create_agent(spec)


# --- Multi-agent workspace ---------------------------------------------------
#
# Surface for wisdom-layer 1.2.0+ multi-agent features (shared memory pool,
# agent-to-agent messaging, team dreams). Initialization is lazy — the first
# request to any of these routes (or the first agent boot) attempts
# ``Workspace.initialize()``. License-tier failures are cached and surfaced
# via ``GET /api/workspace/status`` so the SPA can render a CTA without
# every per-agent boot retrying the same failure.


def _resolve_license_key() -> str | None:
    studio_config = load_studio_config()
    return studio_config.license_key or settings.wisdom_layer_license


@app.get("/api/workspace/status")
async def get_workspace_status() -> dict[str, object]:
    """Return whether multi-agent features are available and why not, if not."""
    return await workspace_manager.status(_resolve_license_key())


@app.get("/api/workspace/agents")
async def get_workspace_agents() -> list[dict[str, object]]:
    """Return the workspace agent directory.

    Empty when the workspace is unavailable — the SPA can render the same
    empty state without first checking ``/api/workspace/status``.
    """
    await workspace_manager.ensure_initialized(_resolve_license_key())
    return await workspace_manager.list_agents()


async def _require_workspace() -> object:
    """Return the live :class:`Workspace` or raise 403 with the cached reason.

    Routes that require multi-agent features call this so the SPA gets a
    clean structured error (matching the same shape ``/api/workspace/status``
    returns) instead of an opaque 500. Lazy-initializes on first call so a
    fresh process boot does not require a status ping before any pool route
    can succeed.
    """
    await workspace_manager.ensure_initialized(_resolve_license_key())
    workspace = workspace_manager.workspace
    if workspace is None:
        unavail = workspace_manager.unavailable_reason
        raise HTTPException(
            status_code=403,
            detail={
                "error": "workspace_unavailable",
                "reason": unavail.reason if unavail else "uninitialized",
                "feature": unavail.feature if unavail else None,
                "required_tier": unavail.required_tier if unavail else None,
                "upgrade_url": unavail.upgrade_url if unavail else None,
                "message": (unavail.message if unavail else "Workspace is not initialized."),
            },
        )
    return workspace


def _shared_memory_dict(row: object) -> dict[str, object]:
    """Serialize a :class:`wisdom_layer.workspace.SharedMemory` for JSON.

    Inlining the projection keeps Studio decoupled from the SDK dataclass
    layout — if the SDK adds fields, Studio's response shape stays stable.
    """
    return {
        "id": row.id,  # type: ignore[attr-defined]
        "workspace_id": row.workspace_id,  # type: ignore[attr-defined]
        "contributor_id": row.contributor_id,  # type: ignore[attr-defined]
        "source_memory_id": row.source_memory_id,  # type: ignore[attr-defined]
        "visibility": str(row.visibility),  # type: ignore[attr-defined]
        "content": row.content,  # type: ignore[attr-defined]
        "reason": row.reason,  # type: ignore[attr-defined]
        "endorsement_count": row.endorsement_count,  # type: ignore[attr-defined]
        "contention_count": row.contention_count,  # type: ignore[attr-defined]
        "base_score": row.base_score,  # type: ignore[attr-defined]
        "team_score": row.team_score,  # type: ignore[attr-defined]
        "shared_at": row.shared_at.isoformat(),  # type: ignore[attr-defined]
        "archived_at": (
            row.archived_at.isoformat()  # type: ignore[attr-defined]
            if row.archived_at  # type: ignore[attr-defined]
            else None
        ),
    }


def _team_insight_dict(row: object) -> dict[str, object]:
    return {
        "id": row.id,  # type: ignore[attr-defined]
        "workspace_id": row.workspace_id,  # type: ignore[attr-defined]
        "content": row.content,  # type: ignore[attr-defined]
        "synthesis_prompt_hash": row.synthesis_prompt_hash,  # type: ignore[attr-defined]
        "contributor_count": row.contributor_count,  # type: ignore[attr-defined]
        "dream_cycle_id": row.dream_cycle_id,  # type: ignore[attr-defined]
        "created_at": row.created_at.isoformat(),  # type: ignore[attr-defined]
        "archived_at": (
            row.archived_at.isoformat()  # type: ignore[attr-defined]
            if row.archived_at  # type: ignore[attr-defined]
            else None
        ),
    }


# --- Shared memory pool ------------------------------------------------------


@app.post("/api/agents/{agent_id}/memory/{memory_id}/share")
async def share_memory(
    agent_id: str,
    memory_id: str,
    body: dict[str, object] | None = None,
) -> dict[str, object]:
    """Promote one of an agent's memories into the workspace shared pool.

    Calls ``agent.memory.share`` — the bridge enforces tenancy (the agent
    can only share its own memories). Body is optional:
    ``{ "visibility"?: "TEAM"|"PUBLIC", "reason"?: string }``.
    """
    await _require_workspace()

    # Validate the request shape BEFORE any side effects (session creation,
    # workspace mutation). PRIVATE is a contract violation, not a "not found"
    # condition — surface 422 even if the agent_id happens to be unknown.
    payload = body or {}
    visibility_raw = payload.get("visibility", "TEAM")
    reason = str(payload.get("reason", "") or "")

    from wisdom_layer.workspace import Visibility

    try:
        visibility = Visibility(str(visibility_raw))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid visibility: {exc}") from exc
    if visibility is Visibility.PRIVATE:
        raise HTTPException(status_code=422, detail="cannot share with PRIVATE visibility")

    try:
        session = await session_manager.get_or_create(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        shared_id = await session.agent.memory.share(
            memory_id, visibility=visibility, reason=reason
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"shared_memory_id": shared_id}


@app.get("/api/workspace/shared-memory")
async def list_shared_memory(
    contributor_id: str | None = None,
    min_base_score: float | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    workspace = await _require_workspace()
    rows = await workspace.pool.list(  # type: ignore[attr-defined]
        contributor_id=contributor_id,
        min_base_score=min_base_score,
        limit=limit,
    )
    return [_shared_memory_dict(r) for r in rows]


@app.post("/api/workspace/shared-memory/{shared_id}/endorse")
async def endorse_shared_memory(shared_id: str, body: dict[str, object]) -> dict[str, object]:
    workspace = await _require_workspace()
    agent_id = str(body.get("agent_id", "") or "").strip()
    if not agent_id:
        raise HTTPException(status_code=422, detail="agent_id is required")
    recorded = await workspace.pool.endorse(  # type: ignore[attr-defined]
        shared_id, endorsing_agent_id=agent_id
    )
    return {"recorded": recorded}


@app.post("/api/workspace/shared-memory/{shared_id}/contest")
async def contest_shared_memory(shared_id: str, body: dict[str, object]) -> dict[str, object]:
    workspace = await _require_workspace()
    agent_id = str(body.get("agent_id", "") or "").strip()
    reason = str(body.get("reason", "") or "").strip()
    if not agent_id:
        raise HTTPException(status_code=422, detail="agent_id is required")
    if not reason:
        raise HTTPException(status_code=422, detail="reason is required for a contest")
    recorded = await workspace.pool.contest(  # type: ignore[attr-defined]
        shared_id, contesting_agent_id=agent_id, reason=reason
    )
    return {"recorded": recorded}


# --- Team insights + Team Dream ---------------------------------------------


@app.get("/api/workspace/team-insights")
async def list_team_insights(limit: int = 50) -> list[dict[str, object]]:
    """Return synthesized team insights, newest-first.

    Backed by a direct backend query because the SDK does not expose a
    public ``pool.list_insights(...)`` method in v1.2.0 — the workspace
    backend has the rows; we read them through it. Empty list when the
    workspace is unavailable.
    """
    workspace = workspace_manager.workspace
    if workspace is None:
        return []
    rows = await workspace.pool.list_team_insights(limit=limit)  # type: ignore[attr-defined]
    return [_team_insight_dict(r) for r in rows]


@app.post("/api/workspace/team-dream")
async def run_team_dream(body: dict[str, object]) -> dict[str, object]:
    """Run a Team Dream Phase-1 synthesis cycle.

    Requires a designated synthesizer agent — the LLM call is made with
    that agent's adapter, since the workspace itself has no LLM bound.
    Body: ``{ "synthesizer_agent_id": str, "min_contributors"?: int }``.
    """
    workspace = await _require_workspace()
    synthesizer_id = str(body.get("synthesizer_agent_id", "") or "").strip()
    if not synthesizer_id:
        raise HTTPException(status_code=422, detail="synthesizer_agent_id is required")
    min_contributors = int(body.get("min_contributors", 2) or 2)

    try:
        session = await session_manager.get_or_create(synthesizer_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    insight = await workspace.team_synthesize(  # type: ignore[attr-defined]
        synthesizer=session.agent,
        min_contributors=min_contributors,
    )
    if insight is None:
        return {
            "synthesized": False,
            "reason": "below_threshold",
            "min_contributors": min_contributors,
        }
    return {"synthesized": True, "insight": _team_insight_dict(insight)}


@app.get("/api/workspace/team-insights/{insight_id}/provenance")
async def walk_team_insight_provenance(insight_id: str) -> dict[str, object]:
    """Walk a team insight's contributor chain — the patent-defensible moat.

    Returns the team insight, its contributing shared memories, and each
    contributor's opaque ``source_memory_id`` back-pointer. The walk
    deliberately never dereferences private content; only the contributing
    agent itself can resolve those ids.
    """
    workspace = await _require_workspace()
    try:
        provenance = await workspace.pool.walk_provenance(insight_id)  # type: ignore[attr-defined]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "team_insight": _team_insight_dict(provenance.team_insight),
        "contributions": [
            {
                "shared_memory_id": c.shared_memory_id,
                "contributor_agent_id": c.contributor_agent_id,
                "source_memory_id": c.source_memory_id,
                "shared_content": c.shared_content,
                "contribution_weight": c.contribution_weight,
            }
            for c in provenance.contributions
        ],
    }


# --- Agent-to-agent messaging (MessageBus) ----------------------------------


def _message_dict(msg: object) -> dict[str, object]:
    """Project an :class:`AgentMessage` into a JSON-stable dict.

    The SDK dataclass may grow fields across patch releases — pinning the
    wire shape here means the SPA does not silently break on additions.
    """
    return {
        "id": msg.id,  # type: ignore[attr-defined]
        "workspace_id": msg.workspace_id,  # type: ignore[attr-defined]
        "sender_id": msg.sender_id,  # type: ignore[attr-defined]
        "recipient_id": msg.recipient_id,  # type: ignore[attr-defined]
        "broadcast_capability": msg.broadcast_capability,  # type: ignore[attr-defined]
        "content": msg.content,  # type: ignore[attr-defined]
        "purpose": str(msg.purpose),  # type: ignore[attr-defined]
        "thread_id": msg.thread_id,  # type: ignore[attr-defined]
        "in_reply_to": msg.in_reply_to,  # type: ignore[attr-defined]
        "expects_reply": msg.expects_reply,  # type: ignore[attr-defined]
        "status": str(msg.status),  # type: ignore[attr-defined]
        "created_at": msg.created_at.isoformat(),  # type: ignore[attr-defined]
        "read_at": msg.read_at.isoformat() if msg.read_at else None,  # type: ignore[attr-defined]
        "replied_at": (
            msg.replied_at.isoformat() if msg.replied_at else None  # type: ignore[attr-defined]
        ),
        "is_broadcast": msg.is_broadcast,  # type: ignore[attr-defined]
    }


def _coerce_purpose(value: object) -> object:
    """Map a JSON ``purpose`` string into the SDK enum, defaulting to QUESTION."""
    from wisdom_layer.workspace.messages import MessagePurpose

    raw = str(value or "").strip().lower() or "question"
    try:
        return MessagePurpose(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid purpose: {raw}") from exc


@app.post("/api/workspace/messages")
async def send_message(body: dict[str, object]) -> dict[str, object]:
    """Send a directed agent-to-agent message.

    Body: ``{ sender_id, recipient_id, content, purpose?, expects_reply? }``.
    """
    workspace = await _require_workspace()
    sender_id = str(body.get("sender_id", "") or "").strip()
    recipient_id = str(body.get("recipient_id", "") or "").strip()
    content = str(body.get("content", "") or "")
    if not sender_id or not recipient_id or not content.strip():
        raise HTTPException(
            status_code=422,
            detail="sender_id, recipient_id, and non-empty content are required",
        )
    purpose = _coerce_purpose(body.get("purpose", "question"))
    expects_reply = bool(body.get("expects_reply", True))
    try:
        message_id = await workspace.messages.send(  # type: ignore[attr-defined]
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=content,
            purpose=purpose,
            expects_reply=expects_reply,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"message_id": message_id}


@app.post("/api/workspace/messages/broadcast")
async def broadcast_message(body: dict[str, object]) -> dict[str, object]:
    """Broadcast to every agent matching ``broadcast_capability``.

    Body: ``{ sender_id, broadcast_capability, content, purpose? }``.
    Use ``broadcast_capability="general"`` to reach the whole workspace.
    """
    workspace = await _require_workspace()
    sender_id = str(body.get("sender_id", "") or "").strip()
    capability = str(body.get("broadcast_capability", "") or "").strip()
    content = str(body.get("content", "") or "")
    if not sender_id or not capability or not content.strip():
        raise HTTPException(
            status_code=422,
            detail="sender_id, broadcast_capability, and non-empty content are required",
        )
    purpose = _coerce_purpose(body.get("purpose", "information"))
    try:
        message_id = await workspace.messages.broadcast(  # type: ignore[attr-defined]
            sender_id=sender_id,
            broadcast_capability=capability,
            content=content,
            purpose=purpose,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"message_id": message_id}


@app.post("/api/workspace/messages/{message_id}/reply")
async def reply_to_message(message_id: str, body: dict[str, object]) -> dict[str, object]:
    """Reply on the same thread as ``message_id``."""
    workspace = await _require_workspace()
    sender_id = str(body.get("sender_id", "") or "").strip()
    content = str(body.get("content", "") or "")
    if not sender_id or not content.strip():
        raise HTTPException(
            status_code=422,
            detail="sender_id and non-empty content are required",
        )
    purpose = _coerce_purpose(body.get("purpose", "information"))
    try:
        reply_id = await workspace.messages.reply(  # type: ignore[attr-defined]
            sender_id=sender_id,
            in_reply_to=message_id,
            content=content,
            purpose=purpose,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"message_id": reply_id}


@app.get("/api/workspace/agents/{agent_id}/inbox")
async def get_inbox(
    agent_id: str,
    unread_only: bool = False,
    include_broadcasts: bool = True,
    limit: int = 100,
) -> list[dict[str, object]]:
    """Return the inbox for ``agent_id`` — directed + capability broadcasts."""
    workspace = await _require_workspace()
    # Look up the agent's capabilities so the bus can resolve broadcasts.
    record = await workspace.directory.get(agent_id)  # type: ignore[attr-defined]
    capabilities = list(record.capabilities) if record else ["general"]
    rows = await workspace.messages.list_inbox(  # type: ignore[attr-defined]
        recipient_id=agent_id,
        recipient_capabilities=capabilities,
        unread_only=unread_only,
        include_broadcasts=include_broadcasts,
        limit=limit,
    )
    return [_message_dict(m) for m in rows]


@app.get("/api/workspace/threads/{thread_id}")
async def get_thread(thread_id: str, limit: int = 200) -> list[dict[str, object]]:
    """Return every message on a thread, oldest-first."""
    workspace = await _require_workspace()
    rows = await workspace.messages.list_thread(thread_id, limit=limit)  # type: ignore[attr-defined]
    return [_message_dict(m) for m in rows]


@app.post("/api/workspace/messages/{message_id}/read")
async def mark_message_read(message_id: str, body: dict[str, object]) -> dict[str, object]:
    """Mark ``message_id`` as read by ``agent_id``."""
    workspace = await _require_workspace()
    agent_id = str(body.get("agent_id", "") or "").strip()
    if not agent_id:
        raise HTTPException(status_code=422, detail="agent_id is required")
    recorded = await workspace.messages.mark_read(  # type: ignore[attr-defined]
        message_id=message_id, reader_agent_id=agent_id
    )
    return {"recorded": recorded}


# --- Chat disclosure helpers -------------------------------------------------


_MEMORY_SNIPPET_MAX = 240
_MEMORY_DISCLOSURE_LIMIT = 5
_DIRECTIVE_DISCLOSURE_LIMIT = 10


def _short_memory_snippet(memory: dict[str, object]) -> str:
    """Extract a one-line, length-bounded snippet from a memory dict.

    SDK memory rows surface a ``content`` dict (varying schema by ``kind``).
    We try the most informative shapes first and fall back to a JSON dump.
    """
    raw_content = memory.get("content")
    text = ""
    if isinstance(raw_content, dict):
        if isinstance(raw_content.get("text"), str):
            text = str(raw_content["text"])
        elif isinstance(raw_content.get("role"), str) and isinstance(raw_content.get("text"), str):
            text = f"{raw_content['role']}: {raw_content['text']}"
        else:
            text = ", ".join(f"{k}={v}" for k, v in raw_content.items())
    elif isinstance(raw_content, str):
        text = raw_content
    text = text.strip()
    if len(text) > _MEMORY_SNIPPET_MAX:
        text = text[: _MEMORY_SNIPPET_MAX - 1].rstrip() + "…"
    return text


async def _gather_memory_snippets(agent: object, query: str) -> list[str]:
    """Return short snippets of the memories most relevant to ``query``.

    Failures are logged and swallowed — disclosure is best-effort.
    """
    try:
        memories = await agent.memory.search(query, limit=_MEMORY_DISCLOSURE_LIMIT)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — logged, swallowed; chat must still complete
        logger.debug("studio.chat.memory_disclosure_failed", exc_info=True)
        return []
    snippets: list[str] = []
    for mem in memories:
        if not isinstance(mem, dict):
            continue
        snippet = _short_memory_snippet(mem)
        if snippet:
            snippets.append(snippet)
    return snippets


async def _gather_directive_snippets(agent: object) -> list[str]:
    """Return the active directive texts the agent's runtime would apply.

    Mirrors the SDK Compare endpoint's behavior so Studio's two chat surfaces
    stay consistent. Failures are logged and swallowed.
    """
    try:
        directives = await agent.directives.active()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        logger.debug("studio.chat.directive_disclosure_failed", exc_info=True)
        return []
    out: list[str] = []
    for entry in directives[:_DIRECTIVE_DISCLOSURE_LIMIT]:
        if isinstance(entry, dict):
            text = entry.get("text") or entry.get("content")
            if isinstance(text, str) and text.strip():
                out.append(text.strip())
        elif isinstance(entry, str) and entry.strip():
            out.append(entry.strip())
    return out


# --- Session state (kiosk / ephemeral) ---------------------------------------


def _session_state_response(state: SessionState) -> JSONResponse:
    """Return a 410 with the same structured body the SPA expects for end-states.

    410 Gone is the right semantic — the resource (chat session) has been
    intentionally retired and won't come back without a fresh container. The
    body carries enough data for the SPA to render the configured CTA
    without re-fetching ``/api/config``.
    """
    return JSONResponse(
        status_code=410,
        content={
            "error": state.state,
            "agent_id": state.agent_id,
            "tokens_used": state.tokens_used,
            "token_cap": state.token_cap,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            "expires_at": state.expires_at.isoformat() if state.expires_at else None,
        },
    )


@app.get("/api/agents/{agent_id}/session", response_model=SessionState)
async def get_session_state(agent_id: str) -> SessionState:
    """Return the live session state. Polled by the SPA's session-timer view."""
    try:
        session = await session_manager.get_or_create(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await session.refresh_state()


# --- Chat (thin wrapper around SDK respond_loop) -----------------------------


@app.post("/api/agents/{agent_id}/chat", response_model=ChatResponse)
async def chat(agent_id: str, request: ChatRequest) -> Response:
    """Single-turn chat backed by the SDK reference integration helper.

    The SDK dashboard's own ``/api/chat`` route is a baseline-vs-wisdom *demo*
    comparison endpoint. Studio's chat panel wants a normal single-answer
    chat, so we wrap :func:`respond_loop` directly. Memory capture is on by
    default so context accrues across turns.
    """
    try:
        session = await session_manager.get_or_create(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async with session.lock:
        # Defense-in-depth gate. The frontend renders an end-state view as
        # soon as the cap or TTL trips, but we re-check here so a scripted
        # client that ignores the SPA banner can't keep burning tokens.
        state = await session.refresh_state()
        if state.state != "active":
            return _session_state_response(state)

        if request.capture:
            await session.agent.memory.capture(
                "conversation",
                {"role": "user", "text": request.message},
            )

        # Thread the SPA-tracked prior turns into the SDK's layer-4 context.
        # The SDK only auto-threads memory (semantic), not chronological
        # history, so without this each turn is treated as standalone and
        # the agent can't resolve pronouns ("track them down" → "who is
        # them?"). Map the wire format ({role, content}) to plain dicts;
        # the SDK reads dict.get("role") / dict.get("content").
        session_context = (
            [{"role": m.role, "content": m.content} for m in request.prior_messages]
            if request.prior_messages
            else None
        )

        result = await respond_loop(
            session.agent,
            request.message,
            hard_constraints=session.detail.persona,
            session_context=session_context,
        )

        # Re-run the searches respond_loop did internally so the SPA can
        # show "what informed this answer" without depending on SDK-internal
        # state. Disclosure is a transparency affordance — failures here are
        # logged and swallowed so the chat itself still completes.
        memory_snippets = await _gather_memory_snippets(session.agent, request.message)
        directive_snippets = await _gather_directive_snippets(session.agent)

        if request.capture:
            await session.agent.memory.capture(
                "conversation",
                {"role": "agent", "text": result.response},
            )

        # Refresh after the LLM call so the next request sees the post-call
        # token total. If this turn pushed us over the cap, the *next* request
        # will be rejected — this turn's response is honored (we already paid
        # for it).
        await session.refresh_state()

        return JSONResponse(
            content=ChatResponse(
                response=result.response,
                memories_used=result.memories_used,
                composed_chars=result.composed_chars,
                truncated_layers=result.truncated_layers,
                snapshot_id=result.snapshot_id,
                memories_used_snippets=memory_snippets,
                directives_used=directive_snippets,
            ).model_dump()
        )


# --- Cognition WebSocket -----------------------------------------------------


@app.websocket("/ws/cognition/{agent_id}")
async def cognition_socket(websocket: WebSocket, agent_id: str) -> None:
    """Stream SDK events for a single agent via the SDK ``WebSocketHub``.

    Messages arrive as JSON arrays of ``{"type", "timestamp", "data"}`` events
    (the SDK hub batches events on a 100 ms flush interval).

    Handshake order matters: ``websocket.accept()`` is called *before*
    ``session_manager.get_or_create``. Cold session boot does license
    validation, SQLite init, and a sentence-transformers cold load that can
    take several seconds — long enough for the browser/proxy to give up and
    surface ``connection rejected (400 Bad Request)``. Accepting first
    completes the WS upgrade immediately; any failure during boot is then
    reported as a clean application close code (4404 / 4500) with a
    human-readable reason.
    """
    await websocket.accept()
    try:
        session = await session_manager.get_or_create(agent_id)
    except KeyError:
        await websocket.close(code=4404, reason=f"agent not found: {agent_id}")
        return
    except Exception as exc:  # noqa: BLE001 — surface every boot failure
        logger.exception("studio.ws.session_boot_failed", extra={"agent_id": agent_id})
        # WS close-reason is capped at 123 bytes; truncate the message so we
        # never produce an invalid frame.
        reason = f"session boot failed: {exc}"[:120]
        await websocket.close(code=4500, reason=reason)
        return

    # First WS connect anchors the session-TTL clock. ``mark_started`` is
    # idempotent — bouncing the WebSocket can't reset a visitor's countdown.
    await session.mark_started()

    # We've already accepted the socket above, so we can't call
    # ``session.hub.connect(ws)`` (the SDK hub does its own ``ws.accept()``
    # which would raise on a second call). Register directly on the hub's
    # client set instead. The hub's ``disconnect`` is symmetric and only
    # discards from this set, so cleanup remains correct.
    session.hub._clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        session.hub.disconnect(websocket)


# --- Static SPA serve (production single-port image) -------------------------
#
# When STUDIO_STATIC_DIR is set (Docker image bakes the SPA at /app/static),
# the same uvicorn process serves the UI alongside the API. In development this
# is unset and Vite owns the frontend, so the catch-all is not registered and
# `/agents/{id}` mounts can be appended freely.
#
# IMPORTANT: when registered, this catch-all matches every unhandled GET and
# would intercept dynamic per-session `/agents/{id}` mounts added by
# SessionManager later. We stash the route on `app.state.spa_fallback_route`
# so SessionManager can insert per-session mounts immediately before it,
# preserving precedence.

app.state.spa_fallback_route = None

if settings.static_dir is not None:
    _STATIC_DIR = settings.static_dir.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str, request: Request) -> Response:
        # API and WebSocket paths must never fall through to the SPA — return
        # a clean 404 so JSON clients see the expected shape.
        if full_path.startswith(("api/", "ws/")):
            raise HTTPException(status_code=404, detail="Not Found")

        # Try to serve a real file from the SPA build (assets, favicon, etc.).
        if full_path:
            target = (_STATIC_DIR / full_path).resolve()
            try:
                target.relative_to(_STATIC_DIR)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail="Not Found") from exc
            if target.is_file():
                return FileResponse(target)

        # SPA fallback: only return index.html when the client expects HTML
        # (browser navigation). XHR clients see a real 404.
        accept = request.headers.get("accept", "")
        if full_path and "text/html" not in accept:
            raise HTTPException(status_code=404, detail="Not Found")

        index = _STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Not Found")

    app.state.spa_fallback_route = app.router.routes[-1]
