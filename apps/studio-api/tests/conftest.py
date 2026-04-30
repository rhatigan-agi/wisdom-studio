"""Test fixtures for the Studio API.

Each test gets an isolated `WISDOM_STUDIO_DATA_DIR` so persistence tests do not
clobber a developer's local agents directory.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def studio_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))

    # Reload modules so they pick up the new data_dir setting.
    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        yield client
