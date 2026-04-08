"""
vaaniq-voice-server — standalone Pipecat voice pipeline server.

Handles all Twilio voice traffic (inbound TwiML, outbound TwiML, status
callbacks, Media Streams WebSocket). Deployed close to Twilio's media
edge (Fly.io iad) while vaaniq-server runs on Railway.

Local development:
    uv run uvicorn vaaniq.voice_server.main:app --port 8001 --reload

Production (Fly.io):
    fly deploy  (fly.toml points here)
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from vaaniq.server.core.config import settings
from vaaniq.server.core.observability import setup_observability
from vaaniq.voice_server.router import router as voice_router

# Register all SQLAlchemy models so Base.metadata has the full table graph
# and foreign key resolution works correctly (e.g. sessions.org_id → organizations).
# vaaniq-server/main.py does the same thing via router imports; we do it explicitly here.
import vaaniq.server.auth.models          # noqa: F401 — users, organizations, org_members
import vaaniq.server.agents.models        # noqa: F401 — agents
import vaaniq.server.models.session       # noqa: F401 — sessions
import vaaniq.server.voice.models         # noqa: F401 — phone_numbers
import vaaniq.server.models.integration    # noqa: F401 — api_keys / integrations

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_observability()

    from vaaniq.server.admin.platform_cache import reload as reload_platform_cache
    from vaaniq.server.chat.checkpointer import setup_checkpointer
    from vaaniq.server.core.database import async_session_factory
    from vaaniq.voice.services.vad import preload_vad

    # 1. Set up the AsyncPostgresSaver — must happen before prewarm so graphs
    #    are compiled with the Postgres checkpointer, not MemorySaver.
    #    State written during voice calls survives server restarts and is
    #    readable by any machine in a multi-instance deployment.
    await setup_checkpointer()
    log.info("checkpointer_ready", checkpointer_type="AsyncPostgresSaver")

    async with async_session_factory() as db:
        # 2. Load platform config (Twilio creds, webhook URLs) into memory cache.
        await reload_platform_cache(db)

        # 3. Pre-load Silero VAD model — pays the ~100ms disk read once at startup
        #    instead of on the first caller's call.
        await preload_vad()

        # 4. Pre-compile all active agents' graphs into the in-process cache so
        #    the first call to each agent doesn't pay compilation cost.
        await _prewarm_graph_cache(db)

    log.info("voice_server_started", voice_server_url=settings.voice_server_url)
    yield
    log.info("voice_server_stopped")


async def _prewarm_graph_cache(db) -> None:
    """
    Compile all active agents' graphs at startup and store them in the cache.
    Best-effort: individual failures are logged but don't block startup.

    The Postgres checkpointer must be set up before this is called so graphs
    are compiled with AsyncPostgresSaver, not MemorySaver.
    """
    from vaaniq.graph.cache import get_or_compile
    from vaaniq.server.agents.repository import AgentRepository
    from vaaniq.server.chat.checkpointer import get_checkpointer
    from vaaniq.server.integrations.service import PostgresCredentialStore

    try:
        checkpointer = get_checkpointer()
    except RuntimeError:
        checkpointer = None  # local dev without Postgres — MemorySaver fallback

    agents = await AgentRepository(db).list_all_active()
    if not agents:
        log.info("graph_cache_prewarm_skipped", reason="no_active_agents")
        return

    log.info("graph_cache_prewarm_start", agent_count=len(agents))
    warmed = 0
    for agent in agents:
        if not agent.graph_config:
            continue
        try:
            org_keys = await PostgresCredentialStore(db).get_org_keys(str(agent.org_id))
            await get_or_compile(
                agent_id=str(agent.id),
                graph_version=agent.graph_version or 1,
                graph_config=agent.graph_config,
                org_keys=org_keys,
                checkpointer=checkpointer,
            )
            warmed += 1
        except Exception:
            log.exception("graph_cache_prewarm_agent_failed", agent_id=str(agent.id))

    log.info("graph_cache_prewarm_complete", warmed=warmed, total=len(agents))


app = FastAPI(
    title="Vaaniq Voice Server",
    version="0.1.0",
    lifespan=lifespan,
    # Only expose docs in development
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url=None,
)

app.include_router(voice_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "vaaniq-voice-server"}
