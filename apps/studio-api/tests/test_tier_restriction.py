"""Tests for the TierRestrictionError → HTTP handler.

The SDK raises this in two distinct shapes, and Studio surfaces them via
distinct HTTP status codes (403 for feature-gate, 402 for cap) so generic
clients can branch on the status alone. We don't go through the chat
endpoint here — that would require a real agent — instead we register a
test-only route on the app that raises the canonical error.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from wisdom_layer.errors import TierRestrictionError


def _attach_tripwire(client: TestClient, exc: TierRestrictionError) -> None:
    """Add a single-shot route that raises ``exc`` so the handler runs."""
    app = client.app

    @app.get("/__tier_tripwire__")
    async def _tripwire() -> None:
        raise exc


def test_tier_restriction_feature_gate_returns_403(studio_app: TestClient) -> None:
    _attach_tripwire(
        studio_app,
        TierRestrictionError(feature="dreams", required_tier="Pro"),
    )
    response = studio_app.get("/__tier_tripwire__")
    assert response.status_code == 403
    body = response.json()
    assert body["error"] == "feature_gated"
    assert body["feature"] == "dreams"
    assert body["required_tier"] == "Pro"
    assert body["upgrade_url"]
    assert body["message"]


def test_tier_restriction_cap_returns_402(studio_app: TestClient) -> None:
    _attach_tripwire(
        studio_app,
        TierRestrictionError(
            cap_kind="memories",
            current=10_000,
            limit=10_000,
            upgrade_url="https://example.com/upgrade",
        ),
    )
    response = studio_app.get("/__tier_tripwire__")
    assert response.status_code == 402
    body = response.json()
    assert body["error"] == "cap_reached"
    assert body["cap_kind"] == "memories"
    assert body["current"] == 10_000
    assert body["limit"] == 10_000
    assert body["upgrade_url"] == "https://example.com/upgrade"
    assert body["reset_at"] is None


def test_tier_restriction_cap_with_reset_at(studio_app: TestClient) -> None:
    """``messages_30d`` caps include an ISO ``reset_at`` so the SPA can render
    a precise countdown rather than a generic 'try again later' line."""
    reset = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)
    _attach_tripwire(
        studio_app,
        TierRestrictionError(
            cap_kind="messages_30d",
            current=500,
            limit=500,
            reset_at=reset,
        ),
    )
    response = studio_app.get("/__tier_tripwire__")
    assert response.status_code == 402
    body = response.json()
    assert body["cap_kind"] == "messages_30d"
    assert body["reset_at"] == reset.isoformat()
