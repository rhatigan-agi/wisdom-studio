"""Builds per-session SDK sub-apps mounted under ``/agents/{agent_id}``.

Studio is multi-agent; the SDK dashboard is single-agent (one ``app.state.agent``).
We solve the impedance mismatch by giving every active ``AgentSession`` its own
FastAPI sub-app whose ``state.agent`` is bound to that session's agent. The SDK
routers' ``Depends(get_agent)`` resolves against the sub-app's state, so no
dependency override is needed.

The sub-app intentionally omits the SDK's static frontend mount and ``/ws``
WebSocket endpoint — Studio renders its own UI in its own theme, and Studio's
top-level ``/ws/cognition/{agent_id}`` is wired to the SDK ``WebSocketHub``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from wisdom_layer.dashboard.middleware import register_exception_handlers
from wisdom_layer.dashboard.routes import (
    chat,
    cost,
    critic,
    directives,
    dreams,
    facts,
    health,
    journals,
    memory,
    provenance,
    status,
)
from wisdom_layer.dashboard.routes import (
    config as agent_config,
)

from studio_api.settings import settings

if TYPE_CHECKING:
    from wisdom_layer import WisdomAgent


def build_sdk_subapp(agent: WisdomAgent) -> FastAPI:
    """Create a FastAPI sub-app exposing every SDK dashboard route for one agent.

    Routes preserve their canonical SDK paths (``/api/chat``, ``/api/memory/search``,
    ``/api/dreams/trigger``, …). When the parent Studio app mounts this sub-app at
    ``/agents/{agent_id}``, the externally-visible URLs become
    ``/agents/{agent_id}/api/chat``, etc.
    """
    sub = FastAPI(title=f"Wisdom Layer SDK — {agent.agent_id}")
    sub.state.agent = agent
    sub.state.demo_mode = False

    register_exception_handlers(sub)

    for module in (
        health,
        status,
        cost,
        directives,
        critic,
        memory,
        dreams,
        journals,
        provenance,
        agent_config,
        chat,
        facts,
    ):
        sub.include_router(module.router)

    # Browser navigation to `/agents/{id}` (an HTML5 SPA route) lands on this
    # sub-app once a session is active. The SDK exception handler returns JSON
    # 404 by default, which would render as raw JSON in the browser. Catch
    # HTML requests and serve the SPA shell instead. Non-HTML requests still
    # 404 cleanly so XHR clients see the expected shape.
    @sub.get("/{full_path:path}", include_in_schema=False)
    async def sub_spa_fallback(full_path: str, request: Request) -> Response:
        if settings.static_dir is not None and "text/html" in request.headers.get("accept", ""):
            index = settings.static_dir / "index.html"
            if index.is_file():
                return FileResponse(index)
        raise HTTPException(status_code=404, detail=f"Not Found: {full_path}")

    return sub


__all__ = ["build_sdk_subapp"]
