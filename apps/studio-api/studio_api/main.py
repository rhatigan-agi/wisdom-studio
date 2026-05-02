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
