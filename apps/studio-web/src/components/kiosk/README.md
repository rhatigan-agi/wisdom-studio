# Kiosk components

UI surfaces only useful in **locked** or **demo** deployments — conference
booths, marketing-page embeds, "try it now" handoffs, internal-team eval
environments, and similar single-session contexts.

| Component | What it does | Driven by |
|---|---|---|
| `Banner` | Top-of-app sanitized HTML banner for branding/legal copy. | `WISDOM_STUDIO_BANNER_HTML` env var |
| `SessionTimer` | Countdown to a hard session reset; dispatches `SESSION_EXPIRED_EVENT`. | `WISDOM_STUDIO_SESSION_TTL_MINUTES` env var |

## Forking guidance

If your fork has accounts, persistence, or any multi-user durability,
**delete this entire folder** and remove the two imports from
`src/components/Shell.tsx`. Nothing else in Studio depends on this
namespace.

If your fork *is* a kiosk or demo, keep this folder and add new
single-session widgets here so the boundary stays obvious.

See `FORKING.md` at the repo root for the full minimal-fork checklist.
