# Security Policy

Wisdom Studio is the canonical forkable reference application for the
[`wisdom-layer`](https://pypi.org/project/wisdom-layer/) SDK. It ships as a
single-port Docker image (FastAPI backend + React SPA) intended for local-only,
single-user use — either a developer running `docker run -p 3000:3000 ...` on
their laptop, or a forker building their own product on top.

It is **not** a hosted multi-tenant service. Studio assumes the operator
controls the host, the network, and the LLM provider key it is given.

---

## Supported Versions

| Version | Status | Security fixes |
|---|---|---|
| `0.9.x` | Current | Yes |
| `0.8.x` | Previous | Yes (until `1.0.0` ships) |
| `< 0.8` | End-of-life | No |

Studio follows semver on the published GHCR image
(`ghcr.io/rhatigan-agi/wisdom-studio`) and on git tags. The PyPI dependency
on `wisdom-layer` is pinned per release; SDK-level vulnerabilities are
disclosed against the SDK repo at
<https://github.com/rhatigan-agi/wisdom-layer>.

---

## Reporting a Vulnerability

**Do not open a public GitHub issue, pull request, or discussion about
a suspected vulnerability.**

### Contact

- **Email:** `security@wisdomlayer.ai`
- **GitHub Security Advisories:** use the "Report a vulnerability" button
  in the [Security tab](https://github.com/rhatigan-agi/wisdom-studio/security/advisories/new)
  of this repository

### What to include

- Description of the vulnerability and the affected component
  (FastAPI route, frontend bundle, Docker image, env-var contract)
- Studio version (git tag or GHCR image digest) where you observed it
- Minimal reproduction (smallest steps demonstrating the issue)
- Impact assessment (what an attacker could do)
- Any known mitigations or workarounds

### What happens next

1. **Acknowledgement within 72 hours.**
2. **Triage within 7 days.** Severity classified via CVSS 3.1.
3. **Coordinated disclosure.** Default 90-day window from validation.
4. **Fix and release.** Patch release to current supported versions
   (new git tag + new GHCR image).
5. **Advisory.** GitHub Security Advisory published, `CHANGELOG.md` updated.

### In scope

- Authentication / authorization gaps in the FastAPI surface
  (`/api/*` and `/ws/*`)
- Cross-session data leakage (one visitor's agent state visible to another)
- SSRF, SQL injection, command injection, path traversal in Studio code
  (not in upstream SDK code; report those at the SDK repo)
- Container escape or image-baked secrets in
  `ghcr.io/rhatigan-agi/wisdom-studio`
- Dependency vulnerabilities reachable from the published image's
  runtime path (see [`osv-scanner.toml`](./osv-scanner.toml) for the
  current ignore list and rationale)
- HTML/JS injection in the SPA, including via `WISDOM_STUDIO_BANNER_HTML`
  bypass of the `bleach` sanitizer
- Bypasses of the ephemeral / TTL / token-cap chat gates
  (`WISDOM_STUDIO_EPHEMERAL`, `_SESSION_TTL_MINUTES`,
  `_TOKEN_CAP_PER_SESSION`)

### Out of scope

- Vulnerabilities in the upstream `wisdom-layer` SDK
  (report at <https://github.com/rhatigan-agi/wisdom-layer>)
- Vulnerabilities in user-supplied LLM providers (Anthropic, OpenAI,
  Gemini, LiteLLM, Ollama)
- Forks that have changed Studio's defaults (e.g., disabled
  `bleach` sanitization, exposed Studio to the public internet without
  a reverse proxy / auth layer)
- Denial of service via valid API usage on a single-user deployment
  (capacity planning, not security)
- Issues that require operator-side misconfiguration to exploit
  (e.g., binding to `0.0.0.0` on a public network with no firewall)

---

## Threat Model Summary

Studio is a **trusted application** running in a **trusted environment**.
The default deployment posture is:

- One container, one operator, one LLM provider key.
- SQLite storage in a mounted volume, owned by the operator.
- No inbound auth — the operator is the user; access control is the
  operator's responsibility (firewall, reverse proxy, VPN).

Inside that envelope, Studio enforces:

- **Per-session SDK isolation.** One `WisdomAgent` instance per chat
  session; SDK state lives under `WISDOM_STUDIO_DATA_DIR` (default `/data`).
- **Banner sanitization.** `WISDOM_STUDIO_BANNER_HTML` passes through
  `bleach` with a fixed allowlist before render.
- **Optional kiosk hardening.** `WISDOM_STUDIO_HIDE_SETTINGS`,
  `_HIDE_AGENT_CRUD`, `_EPHEMERAL`, `_SESSION_TTL_MINUTES`, and
  `_TOKEN_CAP_PER_SESSION` together let a forker expose Studio as a
  bounded demo without the full agent CRUD surface. **These are
  defense-in-depth, not multi-tenant isolation** — a forker who exposes
  Studio to untrusted users on the public internet is responsible for
  adding their own auth and rate limiting at the edge.
- **No image-baked secrets.** All provider API keys, the optional
  `WISDOM_LAYER_LICENSE`, and forker-specific URLs come from environment
  variables or runtime configuration. The published GHCR image is safe
  to inspect publicly.
- **Pinned dependencies.** Workflows pin GitHub Actions by SHA;
  `apps/studio-api` uses `uv sync --frozen` against `uv.lock`;
  `apps/studio-web` uses `pnpm install --frozen-lockfile` against
  `pnpm-lock.yaml`; the runtime base image is digest-pinned.

---

## Security Contacts

- **Primary:** `security@wisdomlayer.ai` — vulnerability reports and
  coordinated disclosure
- **Privacy / data subject requests:** `privacy@wisdomlayer.ai`
- **Governance / compliance / DPA:** `governance@wisdomlayer.ai`,
  `compliance@wisdomlayer.ai`
- **Fallback:** GitHub Security Advisories on this repository
