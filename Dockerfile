# syntax=docker/dockerfile:1.7
#
# Wisdom Studio — production single-port image.
#
# One container, port 3000 serves the SPA AND the API. SQLite data lives in
# /data (mount a volume to persist). Provider API keys are accepted via env
# (ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_BASE_URL) or
# entered through the first-run wizard in the GUI.
#
# Build:   docker build -t wisdom-studio .
# Run:     docker run -p 3000:3000 -v studio-data:/data \
#              -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY wisdom-studio

# -----------------------------------------------------------------------------
# Stage 1 — build the SPA
# -----------------------------------------------------------------------------
FROM node:20-alpine AS web-builder

WORKDIR /app
RUN corepack enable

COPY apps/studio-web/package.json apps/studio-web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY apps/studio-web/ ./
RUN pnpm build


# -----------------------------------------------------------------------------
# Stage 2 — install Python deps and the studio_api package
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS api-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir uv

WORKDIR /app

# studio-api's pyproject.toml references ../../README.md so that local installs
# pick up the repo-root README. Recreate that layout inside the image.
COPY README.md /README.md
COPY apps/studio-api/pyproject.toml apps/studio-api/uv.lock ./
COPY apps/studio-api/studio_api ./studio_api
RUN uv pip install --system --no-cache '.[all-adapters]'


# -----------------------------------------------------------------------------
# Stage 3 — runtime
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=api-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=api-builder /usr/local/bin /usr/local/bin
COPY --from=api-builder /app/studio_api /app/studio_api
COPY --from=web-builder /app/dist /app/static
COPY examples /app/examples

WORKDIR /app

ENV STUDIO_STATIC_DIR=/app/static \
    WISDOM_STUDIO_EXAMPLES_DIR=/app/examples \
    WISDOM_STUDIO_DATA_DIR=/data \
    WISDOM_STUDIO_API_PORT=3000

VOLUME ["/data"]
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:3000/api/health || exit 1

CMD ["uvicorn", "studio_api.main:app", "--host", "0.0.0.0", "--port", "3000"]
