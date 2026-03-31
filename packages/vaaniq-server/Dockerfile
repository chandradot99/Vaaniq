FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
COPY packages/ packages/

RUN uv sync --no-dev

EXPOSE 8000
