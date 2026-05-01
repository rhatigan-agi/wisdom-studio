# Wisdom Studio

[![ci](https://github.com/rhatigan-agi/wisdom-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/rhatigan-agi/wisdom-studio/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)
[![image](https://img.shields.io/badge/ghcr.io-wisdom--studio-2496ed.svg)](https://github.com/rhatigan-agi/wisdom-studio/pkgs/container/wisdom-studio)

A canonical reference UI for the [Wisdom Layer SDK](https://pypi.org/project/wisdom-layer/).
Spin up an agent in 60 seconds, watch its cognition form in real time, and
fork the whole thing as a starter for your own product.

> **What it is:** the official forkable demo and development environment for
> `pip install wisdom-layer`. Open source, Apache-2.0, single-user, local-only.
>
> **What it isn't:** a SaaS, a hosted product, or a feature roadmap with paying customers.

## Highlights

- **Single-port Docker image.** One container serves both SPA and API. Published to GHCR (`linux/amd64`) on every tag.
- **Compare mode.** Toggle a side-by-side view of one question answered three ways — baseline / memory-only / full-wisdom — so the SDK's contribution is visible without scripted demos.
- **Mobile-responsive.** Slide-in sidebar, slide-up cognition pane, 44px touch targets. Embeddable in marketing sites without breakage.
- **Forker-friendly.** Seven generic env vars shape the deployment without code changes. `kiosk/` namespace and a one-page [`FORKING.md`](./FORKING.md) make it obvious what to keep and what to delete.
- **Real-time cognition stream.** Reads directly from the SDK's `WebSocketHub` — no polling, no shim — so you see memory captures, directive evaluations, and dream cycles as they happen.

## Run in 60 seconds

```bash
docker run -d -p 3000:3000 --name wisdom-studio \
  -v $HOME/.wisdom-studio:/data \
  ghcr.io/rhatigan-agi/wisdom-studio:latest
```

Open <http://localhost:3000>, pick an LLM provider, paste your API key, and
start chatting. State (agents, SQLite databases, settings) lives in
`$HOME/.wisdom-studio` so it survives container restarts.

A Wisdom Layer license key is **optional** — the Free tier works out of the
box. To unlock higher caps, set `WISDOM_LAYER_LICENSE` (or paste the key on
the first-run screen). See the SDK docs for tier details.

## Run for development

```bash
git clone https://github.com/rhatigan-agi/wisdom-studio
cd wisdom-studio

# Backend (FastAPI on :8765)
cd apps/studio-api
uv sync
uv run uvicorn studio_api.main:app --reload --port 8765 &

# Frontend (Vite on :5173, proxies /api and /ws to :8765)
cd ../studio-web
pnpm install
pnpm dev
```

Tests:

```bash
cd apps/studio-api && uv run pytest         # backend
cd apps/studio-web && pnpm tsc --noEmit     # frontend types
cd apps/studio-web && pnpm build            # production bundle
```

## Customize / fork

Studio is shaped for forking. The most common changes don't require code:

| What you want | How |
|---|---|
| Your own welcome banner | `WISDOM_STUDIO_BANNER_HTML='<strong>Demo</strong>'` |
| Lock to one provider/model | `WISDOM_STUDIO_LOCK_PROVIDER=anthropic:claude-haiku-4-5` |
| Hide agent creation/deletion | `WISDOM_STUDIO_HIDE_AGENT_CRUD=true` |
| Hide the settings panel | `WISDOM_STUDIO_HIDE_SETTINGS=true` |
| Pre-seed an agent at boot | `WISDOM_STUDIO_SEED_PATH=examples/seeds/researcher.json` |
| Visible session timer (kiosk) | `WISDOM_STUDIO_SESSION_TTL_MINUTES=15` |
| Cap the LLM tokens any one visitor can spend | `WISDOM_STUDIO_TOKEN_CAP_PER_SESSION=50000` |
| Single-visitor demo / try-it-now box | `WISDOM_STUDIO_EPHEMERAL=true` (no studio.json writes; Settings + agent CRUD hidden; pair with TTL or token cap) |
| CTA shown on the session-ended view | `WISDOM_STUDIO_SESSION_END_CTA_HREF=https://your.signup` `WISDOM_STUDIO_SESSION_END_CTA_LABEL='Make your own'` |
| Custom docs link in the sidebar | `WISDOM_STUDIO_DOCS_URL=https://your.docs/site` |
| Custom signup CTA next to the license-key field | `WISDOM_STUDIO_SIGNUP_URL=https://your.signup/page` |
| Hide the signup CTA entirely (forks without a hosted backend) | `WISDOM_STUDIO_SIGNUP_URL=` (empty) |

See [`examples/seeds/README.md`](./examples/seeds/README.md) for a complete
kiosk-style configuration. Then, if the env knobs aren't enough, fork the
repo — the codebase is intentionally small (≈3k LOC of TypeScript + Python).

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) — repository layout, runtime shape, chat flow, cognition stream, SDK gaps tracked upstream.
- [CHANGELOG.md](./CHANGELOG.md) — release history.
- [CONTRIBUTING.md](./CONTRIBUTING.md) — hard rules, scope, code standards, PR checklist.
- [FORKING.md](./FORKING.md) — what to keep and what to safely delete when forking Studio as a starter.

## Built on

- [`wisdom-layer`](https://pypi.org/project/wisdom-layer/) — the agent SDK that
  powers everything Studio renders.

## License

Apache-2.0 — see [LICENSE](./LICENSE).

The Wisdom Layer SDK itself ships under a separate license. Studio depends on
the published `wisdom-layer` package; review its license at
<https://github.com/rhatigan-agi/wisdom-layer>.
