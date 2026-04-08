FROM python:3.12-slim

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace definition and lockfile first (better layer caching)
COPY pyproject.toml uv.lock ./

# Copy all packages (local — not on PyPI yet)
COPY packages/ packages/

# Install only vaaniq-voice-server and its dependencies.
# --package scopes the install so vaaniq-server-only packages are excluded.
RUN uv sync --package vaaniq-voice-server --frozen --no-dev

# Create non-root user for security
RUN useradd -m appuser
USER appuser

EXPOSE 8080

# Fly.io injects $PORT — always bind to it.
# Single worker: Pipecat pipelines are async, one process handles many concurrent calls.
CMD ["uv", "run", "uvicorn", "vaaniq.voice_server.main:app", "--host", "0.0.0.0", "--port", "8080"]
