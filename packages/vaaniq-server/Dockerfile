FROM python:3.12-slim

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# TODO Sprint 7: once vaaniq-core, vaaniq-graph, vaaniq-voice, vaaniq-rag,
# vaaniq-tools, vaaniq-channels are published to PyPI, replace the block below
# with just: COPY packages/vaaniq-server/ . and uv sync --frozen --no-dev
# They will install from PyPI like any other dependency.

# Copy workspace definition and lockfile first (better layer caching)
COPY pyproject.toml uv.lock ./

# Copy all packages (local — not on PyPI yet)
COPY packages/ packages/

# Create non-root user and transfer ownership before uv sync so the
# .venv is owned by appuser from the start — avoids permission errors
# when the container runtime tries to modify site-packages at startup.
RUN useradd -m appuser && chown -R appuser:appuser /app

USER appuser

# Install only vaaniq-server and its dependencies.
# --package scopes the install to one workspace member, so vaaniq-voice-server
# (which goes to Fly.io) is never built here.
RUN uv sync --package vaaniq-server --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "vaaniq.server.main:app", "--host", "0.0.0.0", "--port", "8000"]
