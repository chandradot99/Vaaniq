from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import vaaniq.server.voice.models  # noqa: F401 — registers PhoneNumber with Base.metadata
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from vaaniq.server.admin.router import router as admin_router
from vaaniq.server.agents.router import router as agents_router
from vaaniq.server.auth.router import router as auth_router
from vaaniq.server.chat.router import router as chat_router
from vaaniq.server.core.config import settings
from vaaniq.server.core.observability import setup_observability
from vaaniq.server.integrations.router import router as integrations_router
from vaaniq.server.middleware.cors import add_cors
from vaaniq.server.tools.router import router as tools_router
from vaaniq.server.voice.router import router as voice_router
from vaaniq.server.webhooks.router import router as webhooks_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_observability()
    from vaaniq.server.admin.platform_cache import reload as reload_platform_cache
    from vaaniq.server.chat.checkpointer import setup_checkpointer
    from vaaniq.server.core.database import async_session_factory
    await setup_checkpointer()
    async with async_session_factory() as db:
        await reload_platform_cache(db)
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
app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(integrations_router)
app.include_router(tools_router)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(webhooks_router)
app.include_router(voice_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    import redis.asyncio as aioredis
    from sqlalchemy import text
    from vaaniq.server.core.database import async_session_factory
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
