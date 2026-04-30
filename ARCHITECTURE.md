# Architecture

This document covers the runtime shape of Wisdom Studio: layout, request flow, and the SDK boundary. For project conventions and contribution rules see [CONTRIBUTING.md](./CONTRIBUTING.md).

## Layout

```
wisdom-studio/
├── apps/
│   ├── studio-api/          # FastAPI backend, control plane over the SDK
│   │   └── studio_api/
│   │       ├── main.py        # Studio's own routes (agent CRUD, chat, /ws)
│   │       ├── settings.py    # process settings (data dir, ports, CORS)
│   │       ├── schemas.py     # Pydantic request/response models
│   │       ├── store.py       # JSON-on-disk agent registry + studio config
│   │       ├── sdk_factory.py # SDK construction (only file that touches WisdomAgent init)
│   │       ├── sdk_mount.py   # builds per-session FastAPI sub-apps with SDK routers
│   │       └── sessions.py    # SessionManager — agent + WebSocketHub + sub-app per id
│   └── studio-web/          # React + Vite + TypeScript SPA
│       └── src/
│           ├── lib/api.ts     # typed fetch wrappers
│           ├── lib/store.ts   # Zustand store (config, agents, cognition stream)
│           ├── types/api.ts   # mirrors of `studio_api.schemas`
│           ├── components/
│           │   ├── Shell.tsx  # shared UI
│           │   └── kiosk/     # opt-in kiosk affordances (Banner, SessionTimer) — safe to delete in a fork
│           └── pages/         # FirstRun, Dashboard, NewAgent, AgentDetail, Settings
├── examples/                # YAML agent configs (+ seeds/ for kiosk pre-seed JSON)
├── docker-compose.yml
└── Dockerfile               # single-port production image (SPA + API on :3000)
```

## Boundaries

Studio's job is the **multi-agent control plane and developer experience**. The SDK's job is **per-agent cognition and operations**. Studio consumes the SDK as a library — importing its routers, instantiating its hub, calling its primitives. Studio does not iframe the SDK's prebuilt frontend, and it does not reimplement functionality the SDK already provides.

- **Studio-owned API** lives under `/api/...`: agent CRUD, examples, first-run config, and a thin `/api/agents/{id}/chat` that wraps `wisdom_layer.integration.respond_loop`.
- **SDK-owned API** is mounted per active session under `/agents/{id}/api/...`. Each `AgentSession` builds a small FastAPI sub-app whose `state.agent` is bound to that session's agent, then includes the SDK's own `chat`, `memory`, `dreams`, `directives`, `status`, `critic`, `journals`, `provenance`, `facts`, `config`, `cost`, and `health` routers. SDK routes resolve against the sub-app's state, so multi-agent dispatch needs no dependency override.
- **Frontend = thin SPA.** All cross-cutting state lives in a single Zustand store. Components render Studio's own UI (zinc theme) calling SDK routes directly via the URL structure above — never via iframe.

## Chat flow

`POST /api/agents/:id/chat` is Studio-owned because it captures a user/agent pair as `conversation` memories around the SDK's reference helper:

1. `agent.memory.capture("conversation", {role: "user", text})`
2. `result = await respond_loop(agent, prompt, hard_constraints=persona)` — single call delegates to the SDK reference integration (snapshot → compose → directives → LLM → respond emit).
3. `agent.memory.capture("conversation", {role: "agent", text: result.response})`

The response shape mirrors `RespondResult` (`response`, `memories_used: int`, `composed_chars`, `truncated_layers`, `snapshot_id`).

The SDK's own `/api/chat` route is *also* mounted, at `/agents/{id}/api/chat`, but it is a baseline-vs-wisdom *comparison* demo, not a single-answer chat — Studio surfaces it from the UI when wanted, but its chat panel uses the Studio wrapper above.

## Cognition stream

`/ws/cognition/{agent_id}` connects directly to the session's `wisdom_layer.dashboard.ws_hub.WebSocketHub`. The hub subscribes to all 47 SDK event names (`_SDK_EVENTS`) and flushes batches every 100 ms, so each WS message is a JSON array of `{type, timestamp, data}`. The frontend store appends per batch.

Each session has its own hub, attached to its own agent — events from agent A cannot bleed to clients of agent B.

## Persistence

Studio writes two artifacts:

- `WISDOM_STUDIO_DATA_DIR/studio.json` — process-level config (license key, provider keys).
- `WISDOM_STUDIO_DATA_DIR/agents/<agent_id>/agent.json` — per-agent manifest.

The per-agent SQLite database is owned by the SDK and lives alongside the manifest at `agents/<agent_id>/agent.db`. Postgres backends use a connection URL stored in the manifest instead.

## Ports

| Surface | Port |
|---|---|
| Backend (FastAPI) | `8765` |
| Frontend dev (Vite) | `5173` (proxies `/api`, `/agents`, and `/ws` to `8765`) |
| Production image | `3000` (single-port serves SPA + API) |

## SDK known gaps

Studio is a dogfooding contract — when we hit an SDK gap, we file it upstream rather than work around it locally. Current gaps tracked against [`wisdom-layer`](https://github.com/rhatigan-agi/wisdom-layer):

| Symbol | Today | Should be |
|---|---|---|
| `MemoryInterface.list` / `.recent` | not exposed; the agent has `agent.memory` but the public memory module exports `Memory`, `MemorySearchResult`, `MemoryStats`, `MemoryTier`, `DeleteReport` only — no list/paginate | list/paginate raw memories without a semantic query, for the memory browser UI; today Studio falls back to `memory.search(query="")` |
| `wisdom-layer[anthropic|openai|gemini]` extras pull `sentence-transformers` (PyTorch) as a hard dep | required because cloud adapters use local embeddings; consequence is a ~5 GB venv even for Anthropic-only installs | optional embedding-backend extras (`wisdom-layer[anthropic,openai-embed]` or similar) so cloud users can route embeddings through their LLM provider and skip PyTorch — directly drives Studio's container image size |
| SDK ships a prebuilt `_static/` dashboard frontend | useful for bare-SDK users; redundant for Studio consumers | open question whether SDK should split into `wisdom-layer` (API-only) and `wisdom-layer[dashboard]` (with prebuilt UI), now that Studio exists as a canonical UI |

**Resolved in 1.1.0:**

- `WisdomAgent.agent_id` — now a public property.
- `AdminDefaults` — now a top-level public export from `wisdom_layer`. Studio imports from `wisdom_layer` directly (no `_internal` path).
- `TierRestrictionError` — now structured with `cap_kind`, `current`, `limit`, `reset_at`, `upgrade_url` fields, mapping cleanly to HTTP 402/403.

When any of these are fixed in a published SDK version, update `studio_api/sdk_factory.py` to use the public symbol and remove the workaround note in code comments.

## What's intentionally not here

- No service mesh — Studio is a single process.
- No auth middleware — single-user only.
- No background queue — dream cycles run inline on demand or on the SDK's own scheduler.
- No analytics/telemetry — the SDK emits its own anonymous install_id telemetry; Studio adds nothing on top.
