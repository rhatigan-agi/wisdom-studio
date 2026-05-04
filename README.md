<div align="center">

<img src="https://raw.githubusercontent.com/rhatigan-agi/wisdom-studio/main/apps/studio-web/public/wisdom-icon.png" width="120" alt="Wisdom Studio" />

# Wisdom Studio

### The canonical forkable reference UI for the [Wisdom Layer SDK](https://pypi.org/project/wisdom-layer/).

**Spin up an agent in 60 seconds, watch its cognition form in real time, fork the whole thing as a starter for your own product.**

<br />

<!-- Release & install -->
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE) [![Docker image](https://img.shields.io/badge/ghcr.io-wisdom--studio-2496ed?logo=docker&logoColor=white)](https://github.com/rhatigan-agi/wisdom-studio/pkgs/container/wisdom-studio) [![Python versions](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776ab?logo=python&logoColor=white)](./apps/studio-api/pyproject.toml) [![Node](https://img.shields.io/badge/node-20-339933?logo=node.js&logoColor=white)](./apps/studio-web/package.json)

<!-- Quality & security -->
[![CI](https://img.shields.io/github/actions/workflow/status/rhatigan-agi/wisdom-studio/ci.yml?branch=main&label=ci&logo=github)](https://github.com/rhatigan-agi/wisdom-studio/actions/workflows/ci.yml) [![CodeQL](https://github.com/rhatigan-agi/wisdom-studio/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/rhatigan-agi/wisdom-studio/actions/workflows/codeql.yml) [![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/rhatigan-agi/wisdom-studio/badge)](https://securityscorecards.dev/viewer/?uri=github.com/rhatigan-agi/wisdom-studio) [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) [![Security policy](https://img.shields.io/badge/security-policy-2ea043)](./SECURITY.md)

<!-- Activity -->
[![Last commit](https://img.shields.io/github/last-commit/rhatigan-agi/wisdom-studio?color=2ea043)](https://github.com/rhatigan-agi/wisdom-studio/commits/main)

</div>

```
                  ┌──────────────────────────────────┐
                  │   Wisdom Studio (you are here)   │
                  │   FastAPI + React, one container │
                  └──────────────┬───────────────────┘
                                 ↓
                       wisdom-layer (PyPI)
                                 ↓
   Any LLM (Anthropic / OpenAI / Gemini / Ollama / LiteLLM)
                                 ↓
              Any Storage Backend (SQLite / Postgres)
```

> **What it is:** the official forkable demo and development environment for
> `pip install wisdom-layer`. Open source, Apache-2.0, single-user, local-only.
>
> **What it isn't:** a SaaS, a hosted product, or a feature roadmap with paying customers.

---

## Highlights

- **Single-port Docker image.** One container serves both SPA and API. Published to GHCR (`linux/amd64`) on every tag, with the base images digest-pinned.
- **Compare mode.** Toggle a side-by-side view of one question answered three ways — baseline / memory-only / full-wisdom — so the SDK's contribution is visible without scripted demos.
- **Real-time cognition stream.** Reads directly from the SDK's `WebSocketHub` — no polling, no shim — so you see memory captures, directive evaluations, and dream cycles as they happen.
- **Multi-agent workspace** _(wisdom-layer 1.2.0+, Enterprise license)_. Shared memory pool, agent-to-agent messaging, Team Dream synthesis, and a provenance walk that exposes the patent-defensible isolation boundary. Three reference agents in [`examples/team_*.yaml`](./examples/) compose into a runnable Researcher → Synthesizer → Critic demo. See the [Workspace](#multi-agent-workspace) section below.
- **Mobile-responsive.** Slide-in sidebar, slide-up cognition pane, 44 px touch targets. Embeddable in marketing sites without breakage.
- **Forker-friendly by default.** Eleven generic env vars shape the deployment without code changes; one-page [`FORKING.md`](./FORKING.md) marks what to keep and what to delete.
- **Procurement-grade hardening.** OpenSSF Scorecard published, CodeQL on every push, SHA-pinned actions, dependency-locked, [`SECURITY.md`](./SECURITY.md) with disclosure policy.

---

## Run in 60 seconds

```bash
docker run -d -p 3000:3000 --name wisdom-studio \
  -v $HOME/.wisdom-studio:/data \
  ghcr.io/rhatigan-agi/wisdom-studio:latest
```

Open <http://localhost:3000>, pick an LLM provider, paste your API key, and start
chatting. State (agents, SQLite databases, settings) lives in `$HOME/.wisdom-studio`
so it survives container restarts.

A Wisdom Layer license key is **optional** — the Free tier works out of the box.
To unlock higher caps, set `WISDOM_LAYER_LICENSE` (or paste the key on the
first-run screen). See the SDK docs for tier details.

---

## Run for development

Prereqs: [`uv`](https://docs.astral.sh/uv/) for the backend, [`pnpm`](https://pnpm.io/installation) (Node 20) for the frontend.

```bash
git clone https://github.com/rhatigan-agi/wisdom-studio
cd wisdom-studio
make dev       # auto-installs deps on first run; Ctrl-C stops both
```

Open <http://localhost:5173>. Backend runs on `:8765`; Vite proxies `/api` and
`/ws` to it.

`make help` lists every target. Common ones:

```bash
make test        # backend pytest + frontend vitest
make lint        # ruff + eslint
make typecheck   # tsc --noEmit
make build       # frontend production bundle
make docker      # build the single-container image locally
```

Prefer two terminals? `make dev-api` and `make dev-web` run them separately.

---

## Multi-agent workspace

The **Workspace** tab (sidebar) surfaces the wisdom-layer 1.2.0 multi-agent
features: a shared memory pool, agent-to-agent messaging, and Team Dream
synthesis. It is license-gated — the SDK's `Workspace.initialize()` raises
on any tier below Enterprise, and Studio caches that gate so single-agent
flows keep working untouched.

The shipped reference flow is a Researcher → Synthesizer → Critic team
that runs entirely from the GUI:

1. **Create** all three agents from the wizard's "Start from example"
   picker (`team_researcher`, `team_synthesizer`, `team_critic`).
2. **Capture and share.** Chat with the researcher and the critic so each
   captures a few memories, then click **Share to workspace** on the
   most useful ones from the agent's Memories pane.
3. **Open the Workspace tab** — the shared pool now lists both agents'
   contributions, with endorse / contest controls.
4. **Run a Team Dream.** In the Team Insights tab, pick the synthesizer
   and click Run. Its LLM produces a single insight that weaves the
   contributions together.
5. **Walk provenance.** Click "Walk provenance" on the resulting
   insight. The modal shows each contribution and its opaque
   `source_memory_id` back-pointer — the patent-defensible isolation
   boundary, where the workspace knows *that* a private memory exists
   without ever seeing *what* it contains.
6. **Send messages.** The Messages tab carries directed and broadcast
   channels for any agent in the workspace. Threads persist server-side
   so reply chains survive page refreshes.

All workspace state lives in `<data_dir>/workspace.db` (SQLite). The
v1.2.0 SDK ships only the SQLite backend; the Postgres backend is
scaffolded for v1.3.0.

---

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
| Cap LLM tokens any one visitor can spend | `WISDOM_STUDIO_TOKEN_CAP_PER_SESSION=50000` |
| Single-visitor demo / try-it-now box | `WISDOM_STUDIO_EPHEMERAL=true` (no `studio.json` writes; Settings + agent CRUD hidden; pair with TTL or token cap) |
| CTA on the session-ended view | `WISDOM_STUDIO_SESSION_END_CTA_HREF=https://your.signup` `WISDOM_STUDIO_SESSION_END_CTA_LABEL='Make your own'` |
| Custom docs link in the sidebar | `WISDOM_STUDIO_DOCS_URL=https://your.docs/site` |
| Custom signup CTA next to the license-key field | `WISDOM_STUDIO_SIGNUP_URL=https://your.signup/page` |
| Hide the signup CTA entirely (forks without a hosted backend) | `WISDOM_STUDIO_SIGNUP_URL=` (empty) |

See [`examples/seeds/README.md`](./examples/seeds/README.md) for a complete
kiosk-style configuration. When the env knobs aren't enough, fork the repo —
the codebase is intentionally small (~3k LOC of TypeScript + Python) and
[`FORKING.md`](./FORKING.md) tells you exactly what's safe to delete.

---

## Security & due diligence

Studio is hardened to the same procurement-grade baseline as the upstream SDK,
so a fork can ship to a security-aware customer without redoing the work:

- **OpenSSF Scorecard published.** Live score on the badge above and on
  [the Scorecard registry](https://securityscorecards.dev/viewer/?uri=github.com/rhatigan-agi/wisdom-studio).
- **CodeQL on every push.** Static analysis across Python (`apps/studio-api`)
  and TypeScript (`apps/studio-web`); results land in the repo's
  [Code Scanning tab](https://github.com/rhatigan-agi/wisdom-studio/security/code-scanning).
- **SHA-pinned GitHub Actions.** Every action in `.github/workflows/` is
  pinned by commit SHA; `permissions: read-all` is the repo-level default,
  with least-privilege opt-ins on the publish job only.
- **Digest-pinned base images.** The `Dockerfile` pins `python:3.12-slim`,
  `node:20-alpine`, and the `uv` binary by `sha256` digest.
- **Locked dependencies.** `apps/studio-api/uv.lock` and
  `apps/studio-web/pnpm-lock.yaml` are checked in and used in CI;
  [`osv-scanner.toml`](./osv-scanner.toml) documents accepted advisories with
  written rationale.
- **Dependabot weekly.** `.github/dependabot.yml` watches GitHub Actions,
  Docker, pip (`apps/studio-api`), and npm (`apps/studio-web`).
- **No image-baked secrets.** All provider API keys, the optional
  `WISDOM_LAYER_LICENSE`, and forker-specific URLs come from environment
  variables — the published GHCR image is safe to inspect publicly.

To report a vulnerability, email `security@wisdomlayer.ai` or use the
[GitHub Security Advisory form](https://github.com/rhatigan-agi/wisdom-studio/security/advisories/new).
Full policy, threat model, supported versions, and additional contacts
(`privacy@`, `governance@`, `compliance@`) live in
[SECURITY.md](./SECURITY.md).

---

## Documentation

| Doc | What's in it |
|---|---|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Repository layout, runtime shape, chat flow, cognition stream, SDK gaps tracked upstream |
| [FORKING.md](./FORKING.md) | What to keep and what to safely delete when forking Studio as a starter |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Hard rules, scope, code standards, PR checklist |
| [SECURITY.md](./SECURITY.md) | Supported versions, disclosure policy, threat model, contacts |
| [CHANGELOG.md](./CHANGELOG.md) | Release history (Keep a Changelog + SemVer) |

---

## Built on

- **[`wisdom-layer`](https://pypi.org/project/wisdom-layer/)** — the agent SDK
  that powers everything Studio renders.
- **FastAPI + Uvicorn** — transport-only backend, one `WisdomAgent` per session.
- **React + Vite + Zustand** — single-page app served from the same container as the API.

---

## License

Apache-2.0 — see [LICENSE](./LICENSE). Fork it, ship it, sell it.

The Wisdom Layer SDK itself ships under a separate license; review it at
<https://github.com/rhatigan-agi/wisdom-layer>. Studio depends on the
published `wisdom-layer` wheel from PyPI and never imports SDK internals.
