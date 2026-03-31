from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from vaaniq.server.core.config import settings
from vaaniq.server.core.observability import setup_observability
from vaaniq.server.middleware.cors import add_cors
from vaaniq.server.routers.v1 import auth, agents
from vaaniq.server.routers import webhooks


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_observability()
    yield


app = FastAPI(
    title="Vaaniq API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url=None,
)

add_cors(app)
Instrumentator().instrument(app).expose(app)

# Routers
app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(webhooks.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    from sqlalchemy import text
    from vaaniq.server.core.database import async_session_factory
    import redis.asyncio as aioredis
    errors: list[str] = []
    try:
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
    except Exception as e:
        errors.append(f"db: {e}")
    try:
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
    except Exception as e:
        errors.append(f"redis: {e}")
    if errors:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail={"errors": errors})
    return {"status": "ready"}
