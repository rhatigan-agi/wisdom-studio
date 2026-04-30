"""Single-port static-serve behavior.

The production Docker image bakes the SPA into the same uvicorn process via
``STUDIO_STATIC_DIR``. These tests verify the resulting routing rules:
real assets are served, HTML5 client routes fall back to ``index.html``, and
``/api/*`` paths still respond as JSON (never as the SPA shell).
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def static_studio_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Boot the Studio app with a fake SPA build wired via ``STUDIO_STATIC_DIR``."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<!doctype html><title>Wisdom Studio SPA</title>")
    (static_dir / "assets").mkdir()
    (static_dir / "assets" / "app.js").write_text("console.log('app');")

    monkeypatch.setenv("STUDIO_STATIC_DIR", str(static_dir))
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path / "data"))

    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    import studio_api.sdk_mount as sdk_mount_module

    importlib.reload(sdk_mount_module)
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        yield client


def test_root_serves_spa_index(static_studio_app: TestClient) -> None:
    response = static_studio_app.get("/", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert "Wisdom Studio SPA" in response.text


def test_api_health_unaffected(static_studio_app: TestClient) -> None:
    response = static_studio_app.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_static_asset_served_directly(static_studio_app: TestClient) -> None:
    response = static_studio_app.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text


def test_html5_route_falls_back_to_index(static_studio_app: TestClient) -> None:
    """A browser visiting `/settings` (a React Router path) gets the SPA shell."""
    response = static_studio_app.get("/settings", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert "Wisdom Studio SPA" in response.text


def test_unknown_api_route_returns_json_404(static_studio_app: TestClient) -> None:
    """`/api/*` must never fall back to the SPA — JSON clients expect a real 404."""
    response = static_studio_app.get("/api/no-such-route")
    assert response.status_code == 404
    assert "html" not in response.headers.get("content-type", "")


def test_unknown_path_with_json_accept_returns_404(static_studio_app: TestClient) -> None:
    """XHR clients (Accept: application/json) must see a 404, not the SPA shell."""
    response = static_studio_app.get(
        "/missing-asset",
        headers={"accept": "application/json"},
    )
    assert response.status_code == 404


def test_path_traversal_blocked(static_studio_app: TestClient) -> None:
    """`/../../etc/passwd` must never resolve outside the static directory."""
    response = static_studio_app.get("/../../etc/passwd", headers={"accept": "text/html"})
    if response.status_code == 200:
        # Falls through to SPA index — never the host filesystem.
        assert "Wisdom Studio SPA" in response.text
    else:
        assert response.status_code == 404


def test_per_agent_mount_has_precedence_over_spa_fallback(
    static_studio_app: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-session SDK mounts inserted at runtime must outrank the catch-all.

    Otherwise XHR calls to `/agents/{id}/api/...` would hit the SPA fallback and
    receive HTML, breaking the SDK dashboard routes.
    """
    import studio_api.sessions as sessions_module

    class _FakeAgent:
        def __init__(self, agent_id: str) -> None:
            self.agent_id = agent_id

        async def initialize(self) -> None:
            return None

        def on(self, _name: str, _handler: object) -> object:
            return object()

        def off(self, _token: object) -> None:
            return None

        async def close(self) -> None:
            return None

    def _fake_build_agent(detail, **_kwargs):  # type: ignore[no-untyped-def]
        return _FakeAgent(detail.agent_id)

    monkeypatch.setattr(sessions_module, "build_agent", _fake_build_agent)

    static_studio_app.post(
        "/api/agents",
        json={"name": "Probe", "archetype": "balanced", "llm_provider": "ollama"},
    )

    import asyncio

    sm = sessions_module.session_manager
    asyncio.run(sm.get_or_create("probe"))

    # The mount must be ahead of the SPA fallback in the route list.
    routes = static_studio_app.app.router.routes
    fallback = static_studio_app.app.state.spa_fallback_route
    assert fallback is not None
    mount = sm._sessions["probe"].mount
    assert routes.index(mount) < routes.index(fallback)
