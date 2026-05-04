# Contributing to Wisdom Studio

Wisdom Studio is the canonical reference application for the [Wisdom Layer SDK](https://pypi.org/project/wisdom-layer/). It is **scaffolding**, not a product. We accept contributions, but we hold a hard line on scope.

For repository layout, runtime architecture, and known SDK gaps see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Hard rules

These are non-negotiable — PRs that violate them will be closed.

- **Studio depends on `wisdom-layer` from PyPI** as a normal dependency. It must **never import SDK internals**. If you find yourself reaching for a private symbol, that's a signal the SDK has a gap. File the gap as an issue against [`wisdom-layer`](https://github.com/rhatigan-agi/wisdom-layer) instead of working around it here. Surfacing real DX gaps is how Studio earns its keep.
- **Single-user, local-only.** No authentication, no multi-tenancy, no hosted-SaaS features. If you need those, fork.
- **Apache-2.0.** Anything that would tie a fork to a specific commercial offering is out of scope.
- **YAML configs in `examples/` map to SDK archetypes.** Adding a new example means picking an existing archetype factory, not bypassing them. If no archetype fits, propose one against the [`wisdom-layer`](https://github.com/rhatigan-agi/wisdom-layer) repo first.

## Scope

**In scope:**

- Bug fixes
- UX improvements to existing surfaces (wizard, chat, cognition sidebar, memory browser, directive inspector, settings)
- Additional LLM adapters (any adapter the SDK supports)
- Additional storage backends (any backend the SDK supports)
- Additional archetype-backed example configs in `examples/`
- Docker / install ergonomics
- Tests, CI, docs

**Out of scope:**

- Authentication or multi-user features
- Hosted-service features (rate limits, quota, billing)
- Custom tools or integrations beyond what the SDK exposes
- Mobile apps
- Marketplace / agent-template hosting
- Anything that papers over an SDK gap inside Studio rather than filing it upstream

If you want one of the out-of-scope items, **fork Studio**. That's what it's for.

## Code standards

### Python (backend)

- Type hints on all function signatures.
- Structured logging — `logger.info("event.name", extra={"key": value})`. No `print()`.
- Prefer `pathlib` over `os.path`. Use context managers for resources.
- No `Any` without a guard. Prefer `unknown`-style narrowing (`isinstance` checks) over typing escape hatches.
- Format with `ruff` and `black`. Lint with `ruff`.

### TypeScript (frontend)

- Explicit return types on exported functions.
- No `any` — use proper types or `unknown` with guards.
- `const` over `let`, never `var`.
- `async/await` over raw promises.
- Early returns to reduce nesting.
- Format with `prettier`, lint with `eslint`.

### Tests

- Test behavior, not implementation.
- Factories for data, mocks only at system boundaries.
- One assertion concept per test.

### Commits

`type(scope): description` with types from `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. One concern per commit.

## Local setup

See [README.md](./README.md) → "Run for development".

### Editor setup (VS Code)

The repo ships a `.vscode/settings.json` that excludes `.venv`, `node_modules`, and the runtime data directory from indexing, file watching, and search. Keep it. It exists because `wisdom-layer` pulls `sentence-transformers` (and therefore PyTorch), which makes the backend venv ~5 GB. Without these exclusions, Pylance and the file watcher will pin a CPU core and consume multi-GB of RAM, eventually crashing the editor.

If you use a different editor, replicate the same exclusions in your tooling (Pyright/ruff already respect `.gitignore`-style patterns; JetBrains users should mark `.venv` and `node_modules` as **Excluded** in *Project Structure*).

If you're on Linux and the editor still feels sluggish after these exclusions, your inotify watch limit may be the bottleneck:

```bash
echo "fs.inotify.max_user_watches=524288" | sudo tee /etc/sysctl.d/99-inotify.conf
sudo sysctl --system
```

## Pull requests

- One concern per PR.
- Include the SDK version you tested against.
- If you touched the cognition stream, list which event names you wired.
- Run validation before pushing (from the repo root):
  - `make typecheck lint test`
  - Smoke test: `make docker && make docker-run`, walk wizard → chat → confirm cognition events land in the sidebar.

## Security

Found a security issue? **Do not open a public issue or PR.** See
[SECURITY.md](./SECURITY.md) for the disclosure policy and contacts
(`security@wisdomlayer.ai`).

If your PR touches dependencies, lockfiles, the Dockerfile, or any
workflow under `.github/workflows/`, please:

- Pin actions by commit SHA (not floating tag).
- Refresh `apps/studio-api/uv.lock` (`uv lock`) and
  `apps/studio-web/pnpm-lock.yaml` (`pnpm install`).
- Run `docker run --rm -v "$(pwd):/src" ghcr.io/google/osv-scanner:latest --recursive /src`
  and either fix any new advisories or document them in
  `osv-scanner.toml` with a written rationale.
