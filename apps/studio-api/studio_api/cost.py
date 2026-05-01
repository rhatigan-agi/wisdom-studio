"""Single touch point between Studio and the SDK's cost subsystem.

Studio enforces a per-session token cap (``WISDOM_STUDIO_TOKEN_CAP_PER_SESSION``)
by summing all input + output tokens consumed since the session began.
Today that sum comes from the SDK's storage backend via
``BaseBackend.cost_summary_aggregate`` — a private surface the SDK exposes
in 1.1.0 but does not yet promise across major versions.

When SDK 1.1.1 ships a public ``cost.recorded`` event, swap the
implementation inside this module to subscribe and accumulate in-process.
Studio's cap-enforcement call sites should not need to change — only the
source of the running total.
"""

from __future__ import annotations

from wisdom_layer import WisdomAgent


async def session_token_total(agent: WisdomAgent, since_iso: str) -> int:
    """Return total input + output tokens recorded for ``agent`` since ``since_iso``.

    ``since_iso`` is an ISO-8601 timestamp (the value Studio records when a
    session is marked started — see ``SessionManager.mark_started``). The SDK
    aggregator filters its cost-records table inclusively from that point.
    Returns 0 when no records exist for the window.
    """
    aggregate = await agent._backend.cost_summary_aggregate(  # noqa: SLF001 — see module docstring
        agent_id=agent.agent_id,
        since=since_iso,
        until=None,
    )
    return int(aggregate.get("total_input_tokens", 0)) + int(
        aggregate.get("total_output_tokens", 0)
    )


__all__ = ["session_token_total"]
