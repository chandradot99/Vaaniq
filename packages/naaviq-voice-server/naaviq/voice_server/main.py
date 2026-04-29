"""
naaviq-voice-server — LiveKit voice pipeline worker + Twilio webhook server.

This process does two things:
  1. FastAPI server: handles Twilio webhook callbacks (inbound, status, recording)
  2. LiveKit worker: connects to LiveKit and processes voice call jobs

When Twilio calls arrive:
  Twilio → POST /webhooks/twilio/voice/inbound → naaviq-server creates LiveKit room
         → TwiML dials into LiveKit SIP → LiveKit dispatches job to THIS worker
         → worker runs NaaviqVoiceAgent until call ends

Local development:
    uv run uvicorn naaviq.voice_server.main:app --port 8001 --reload
    uv run python -m naaviq.voice.worker --dev   ← separate terminal for worker

Production (Fly.io):
    fly deploy  (fly.toml points here)
    CMD runs uvicorn + worker together via the lifespan hook
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
import naaviq.server.agents.models  # noqa: F401

# Register all SQLAlchemy models so Base.metadata has the full table graph.
import naaviq.server.auth.models  # noqa: F401
import naaviq.server.models.integration  # noqa: F401
import naaviq.server.models.session  # noqa: F401
import naaviq.server.voice.models  # noqa: F401
from fastapi import FastAPI
from naaviq.server.core.config import settings
from naaviq.server.core.observability import setup_observability
from naaviq.voice_server.router import router as voice_router

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_observability()

    from naaviq.server.admin.platform_cache import reload as reload_platform_cache
    from naaviq.server.chat.checkpointer import setup_checkpointer
    from naaviq.server.core.database import async_session_factory

    # 1. Set up AsyncPostgresSaver — multi-turn memory persists across restarts.
    await setup_checkpointer()
    log.info("checkpointer_ready", checkpointer_type="AsyncPostgresSaver")

    async with async_session_factory() as db:
        # 2. Load platform config (Twilio creds, webhook URLs) into memory cache.
        await reload_platform_cache(db)

        # 3. Pre-compile active agents' graphs into cache — avoids compile cost
        #    on the first call to each agent.
        await _prewarm_graph_cache(db)

    # 4. Start the LiveKit worker as a background task.
    #    The worker connects to LiveKit and listens for job dispatches.
    worker_task = asyncio.create_task(_run_livekit_worker(), name="livekit_worker")

    log.info("voice_server_started", voice_server_url=settings.voice_server_url)
    yield

    # Shutdown: cancel worker gracefully.
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    log.info("voice_server_stopped")


async def _run_livekit_worker() -> None:
    """
    Run the LiveKit worker in the background alongside the FastAPI server.

    Bypasses cli.run_app() (which parses sys.argv and breaks when called from
    uvicorn) and drives AgentServer.run() directly. The worker connects to
    LiveKit and waits for job dispatches — each incoming call becomes one job.
    """
    try:
        from livekit.agents import WorkerOptions
        from livekit.agents.worker import AgentServer
        from naaviq.voice.worker import entrypoint

        livekit_url = getattr(settings, "livekit_url", "")
        livekit_api_key = getattr(settings, "livekit_api_key", "")
        livekit_api_secret = getattr(settings, "livekit_api_secret", "")

        if not all([livekit_url, livekit_api_key, livekit_api_secret]):
            log.warning(
                "livekit_worker_not_started",
                reason="LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET not set",
            )
            return

        opts = WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="naaviq-voice",  # must match CreateAgentDispatchRequest(agent_name=...)
            ws_url=livekit_url,
            api_key=livekit_api_key,
            api_secret=livekit_api_secret,
        )
        server = AgentServer.from_server_options(opts)
        await server.run()
    except asyncio.CancelledError:
        log.info("livekit_worker_stopped")
        raise
    except Exception:
        log.exception("livekit_worker_crashed")


async def _prewarm_graph_cache(db) -> None:
    """
    Compile all active agents' graphs at startup and store in cache.
    Best-effort: individual failures are logged but don't block startup.
    """
    from naaviq.graph.cache import get_or_compile
    from naaviq.server.agents.repository import AgentRepository
    from naaviq.server.chat.checkpointer import get_checkpointer
    from naaviq.server.integrations.service import PostgresCredentialStore

    try:
        checkpointer = get_checkpointer()
    except RuntimeError:
        checkpointer = None

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
    title="Naaviq Voice Server",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url=None,
)

app.include_router(voice_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "naaviq-voice-server"}
