"""Tests for the auth seam (``studio_api.auth``).

The default Studio posture is single-user/local: ``GET /api/whoami`` resolves
to ``User(id="local")`` for every request. Forks behind an auth proxy opt
into ``WISDOM_STUDIO_TRUST_USER_HEADER`` + ``WISDOM_STUDIO_TRUSTED_PROXY_CIDRS``;
forks with their own JWT/session resolver swap in via ``dependency_overrides``.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _boot_studio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **env: str
) -> TestClient:
    """Boot Studio with an isolated data dir and arbitrary env overrides."""
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.auth as auth_module

    importlib.reload(auth_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    import studio_api.workspace as workspace_module

    importlib.reload(workspace_module)
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    return TestClient(main_module.app)


def _patch_loopback_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the request peer is 127.0.0.1.

    TestClient defaults to ``client=("testclient", 50000)`` — the host part
    is a literal string, not a routable IP, so it never matches a CIDR.
    Must be called *after* ``_boot_studio`` since that reloads the auth
    module and replaces ``_peer_ip`` with a fresh function object.
    """
    import studio_api.auth as auth_module

    monkeypatch.setattr(auth_module, "_peer_ip", lambda _request: "127.0.0.1")


# --- Default behavior -------------------------------------------------------


def test_whoami_default_returns_local_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _boot_studio(tmp_path, monkeypatch) as client:
        response = client.get("/api/whoami")
        assert response.status_code == 200
        assert response.json() == {"id": "local"}


def test_whoami_ignores_header_when_trust_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without trust_user_header configured, a client-supplied header is
    silently ignored — the default resolver never reads it."""
    with _boot_studio(tmp_path, monkeypatch) as client:
        response = client.get(
            "/api/whoami", headers={"X-Authenticated-User": "attacker"}
        )
        assert response.status_code == 200
        assert response.json() == {"id": "local"}


# --- Trust-header path -------------------------------------------------------


def test_trust_header_refuses_untrusted_peer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TestClient's default peer is ``testclient`` (not an IP) — outside any
    CIDR. The seam fails closed with 503 rather than honoring the header."""
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_TRUST_USER_HEADER="X-Authenticated-User",
    ) as client:
        response = client.get(
            "/api/whoami", headers={"X-Authenticated-User": "alice"}
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "auth_proxy_misconfigured"


def test_trust_header_accepts_loopback_peer_with_default_cidrs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``trust_user_header`` set and no explicit CIDR allowlist, the
    default is loopback — same-host proxy is the most common shape."""
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_TRUST_USER_HEADER="X-Authenticated-User",
    ) as client:
        _patch_loopback_peer(monkeypatch)
        response = client.get(
            "/api/whoami", headers={"X-Authenticated-User": "alice"}
        )
        assert response.status_code == 200
        assert response.json() == {"id": "alice"}


def test_trust_header_missing_header_from_trusted_peer_returns_401(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trusted proxy that forgot to write the header — 401, not 200. The
    seam never silently demotes to anonymous when trust is configured."""
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_TRUST_USER_HEADER="X-Authenticated-User",
    ) as client:
        _patch_loopback_peer(monkeypatch)
        response = client.get("/api/whoami")
        assert response.status_code == 401
        assert response.json()["detail"] == "missing_user_header"


def test_trust_header_explicit_cidr_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit CIDR overrides the loopback default. ``10.0.0.0/8`` excludes
    the patched 127.0.0.1 peer, so the request is refused."""
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_TRUST_USER_HEADER="X-Authenticated-User",
        WISDOM_STUDIO_TRUSTED_PROXY_CIDRS="10.0.0.0/8",
    ) as client:
        _patch_loopback_peer(monkeypatch)
        response = client.get(
            "/api/whoami", headers={"X-Authenticated-User": "alice"}
        )
        assert response.status_code == 503


# --- dependency_overrides path ----------------------------------------------


def test_dependency_override_swaps_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The canonical FastAPI seam: forks point ``get_current_user`` at their
    own resolver (JWT, OAuth, session — Studio doesn't care)."""
    with _boot_studio(tmp_path, monkeypatch) as client:
        import studio_api.auth as auth_module
        import studio_api.main as main_module

        def fake_resolver() -> auth_module.User:
            return auth_module.User(id="alice")

        main_module.app.dependency_overrides[auth_module.get_current_user] = (
            fake_resolver
        )
        try:
            response = client.get("/api/whoami")
            assert response.status_code == 200
            assert response.json() == {"id": "alice"}
        finally:
            main_module.app.dependency_overrides.pop(
                auth_module.get_current_user, None
            )


# --- CIDR helpers -----------------------------------------------------------


def test_trusted_proxy_cidrs_default_is_loopback_when_header_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "WISDOM_STUDIO_TRUST_USER_HEADER", "X-Authenticated-User"
    )
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))
    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    assert settings_module.settings.trusted_proxy_cidrs_list == (
        "127.0.0.0/8",
        "::1/128",
    )


def test_trusted_proxy_cidrs_default_empty_when_header_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))
    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    assert settings_module.settings.trusted_proxy_cidrs_list == ()


def test_trusted_proxy_cidrs_parses_comma_separated_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "WISDOM_STUDIO_TRUSTED_PROXY_CIDRS",
        " 10.0.0.0/8 , 192.168.0.0/16 ",
    )
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))
    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    assert settings_module.settings.trusted_proxy_cidrs_list == (
        "10.0.0.0/8",
        "192.168.0.0/16",
    )
