# Wisdom Studio — developer entry point.
#
# `make help` lists every target. The split mirrors the repo layout:
#   apps/studio-api  — FastAPI + uv (Python 3.12)
#   apps/studio-web  — React + pnpm (Node 20)
#
# CI runs the same commands (see .github/workflows/ci.yml). If you change a
# target name, update the README "Run for development" block too.

.DEFAULT_GOAL := help
.PHONY: help install dev dev-api dev-web test test-api test-web lint lint-api lint-web typecheck build docker docker-run clean

API_DIR := apps/studio-api
WEB_DIR := apps/studio-web
API_PORT ?= 8765

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} \
	     /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' \
	     $(MAKEFILE_LIST)

install: $(API_DIR)/.venv $(WEB_DIR)/node_modules ## Install backend (uv) and frontend (pnpm) dependencies

# Sentinel rules. Each sentinel re-runs only when its lockfile/manifest is
# newer, so subsequent `make dev` invocations are instant. `mkdir -p` on
# .venv would defeat uv's own creation, so we let `uv sync` handle it and
# touch the marker after.
$(API_DIR)/.venv: $(API_DIR)/pyproject.toml $(API_DIR)/uv.lock
	cd $(API_DIR) && uv sync --extra dev
	@touch $@

$(WEB_DIR)/node_modules: $(WEB_DIR)/package.json $(WEB_DIR)/pnpm-lock.yaml
	cd $(WEB_DIR) && pnpm install
	@touch $@

dev: $(API_DIR)/.venv $(WEB_DIR)/node_modules ## Run backend + frontend together (auto-installs on first run; Ctrl-C stops both)
	@trap 'kill 0' INT TERM EXIT; \
	(cd $(API_DIR) && uv run uvicorn studio_api.main:app --reload --port $(API_PORT)) & \
	(cd $(WEB_DIR) && pnpm dev) & \
	wait

dev-api: ## Run backend only (uvicorn on :8765)
	cd $(API_DIR) && uv run uvicorn studio_api.main:app --reload --port $(API_PORT)

dev-web: ## Run frontend only (Vite on :5173, proxies /api + /ws to backend)
	cd $(WEB_DIR) && pnpm dev

test: test-api test-web ## Run backend + frontend tests

test-api: ## Run backend pytest suite
	cd $(API_DIR) && uv run pytest tests/ -v

test-web: ## Run frontend vitest suite
	cd $(WEB_DIR) && pnpm test

lint: lint-api lint-web ## Lint backend (ruff) and frontend (eslint)

lint-api: ## Lint backend with ruff
	cd $(API_DIR) && uv run ruff check studio_api tests

lint-web: ## Lint frontend with eslint
	cd $(WEB_DIR) && pnpm lint

typecheck: ## Typecheck the frontend (tsc --noEmit)
	cd $(WEB_DIR) && pnpm typecheck

build: ## Build the frontend production bundle
	cd $(WEB_DIR) && pnpm build

docker: ## Build the single-container production image
	docker build -t wisdom-studio:local .

docker-run: ## Run the locally built image on :3000
	docker run --rm -p 3000:3000 -v $$HOME/.wisdom-studio:/data wisdom-studio:local

clean: ## Remove build artifacts and virtualenvs (leaves node_modules)
	rm -rf $(WEB_DIR)/dist
	rm -rf $(API_DIR)/.venv $(API_DIR)/.pytest_cache
	find $(API_DIR) -type d -name __pycache__ -exec rm -rf {} +
