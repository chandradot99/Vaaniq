"""
Twilio voice webhook handlers + Pipecat WebSocket pipeline endpoint.

All Twilio voice traffic lands here — this server is deployed close to
Twilio's media edge (Fly.io iad) while the main API server (vaaniq-server)
runs on Railway.

No /v1/ prefix — Twilio controls these URLs.
"""

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, Response, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from vaaniq.server.core.database import get_db
from vaaniq.server.webhooks.dependencies import verify_twilio_signature
from vaaniq.server.webhooks.service import VoiceWebhookService

log = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _voice_server_base_url() -> str:
    """
    Return the base URL for the voice server — used to construct the
    WebSocket URL inside TwiML responses.

    Resolution order:
      1. platform_cache["twilio"]["webhook_url"] — set by admin, takes precedence
      2. settings.voice_server_url — env var (VOICE_SERVER_URL)
    """
    from vaaniq.server.admin import platform_cache
    from vaaniq.server.core.config import settings

    platform_twilio = platform_cache.get_provider_config("twilio")
    return ((platform_twilio or {}).get("webhook_url") or settings.voice_server_url).rstrip("/")


# ── Inbound call ──────────────────────────────────────────────────────────────

@router.post("/twilio/voice/inbound", dependencies=[Depends(verify_twilio_signature)])
async def twilio_voice_inbound(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Twilio hits this when a call arrives on one of our numbers.
    Creates a session and returns TwiML opening a Media Stream WebSocket
    pointed at this voice server.
    """
    from vaaniq.voice.transport.twiml import hangup_twiml, inbound_connect_twiml

    session_id = await VoiceWebhookService(db).handle_inbound(CallSid, From, To)
    if session_id is None:
        return Response(
            content=hangup_twiml("Sorry, no agent is configured for this number. Goodbye."),
            media_type="application/xml",
        )
    base = _voice_server_base_url()
    ws_url = f"wss://{base.removeprefix('https://').removeprefix('http://')}/webhooks/twilio/voice/stream/{session_id}"
    return Response(content=inbound_connect_twiml(ws_url), media_type="application/xml")


# ── Outbound call ─────────────────────────────────────────────────────────────

@router.post("/twilio/voice/outbound", dependencies=[Depends(verify_twilio_signature)])
async def twilio_voice_outbound(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Twilio hits this when an outbound call is answered.
    The session already exists — return TwiML connecting it to the WebSocket.
    """
    from vaaniq.voice.transport.twiml import inbound_connect_twiml

    base = _voice_server_base_url()
    ws_url = f"wss://{base.removeprefix('https://').removeprefix('http://')}/webhooks/twilio/voice/stream/{session_id}"

    log.info("voice_outbound_answered", session_id=session_id)
    return Response(content=inbound_connect_twiml(ws_url), media_type="application/xml")


# ── Call status callback ──────────────────────────────────────────────────────

@router.post("/twilio/voice/status", dependencies=[Depends(verify_twilio_signature)])
async def twilio_voice_status(
    background_tasks: BackgroundTasks,
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: str = Form(default="0"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Twilio fires this on every call state transition."""
    result = await VoiceWebhookService(db).handle_status(CallSid, CallStatus, CallDuration)
    if result is not None:
        session_id, org_id = result
        from vaaniq.server.voice.finalization import finalize_voice_session
        background_tasks.add_task(finalize_voice_session, session_id, org_id)
    return Response(content="", status_code=204)


# ── Recording callback ────────────────────────────────────────────────────────

@router.post("/twilio/voice/recording", dependencies=[Depends(verify_twilio_signature)])
async def twilio_voice_recording(
    CallSid: str = Form(...),
    RecordingUrl: str = Form(...),
    RecordingDuration: str = Form(default="0"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Twilio fires this when a call recording is ready."""
    await VoiceWebhookService(db).handle_recording(CallSid, RecordingUrl, RecordingDuration)
    return Response(content="", status_code=204)


# ── Pipecat pipeline WebSocket ────────────────────────────────────────────────

@router.websocket("/twilio/voice/stream/{session_id}")
async def twilio_voice_stream(
    websocket: WebSocket,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Long-lived WebSocket that Twilio's Media Streams connects to.
    Each call gets its own isolated Pipecat pipeline (one asyncio task).
    """
    await websocket.accept()
    log.info("voice_stream_connected", session_id=session_id)
    try:
        from vaaniq.server.voice.context_builder import build_voice_context
        from vaaniq.voice.pipeline.task import run_voice_pipeline

        context = await build_voice_context(
            session_id=session_id,
            websocket=websocket,
            db=db,
        )
        await run_voice_pipeline(websocket=websocket, context=context)
    except WebSocketDisconnect:
        log.info("voice_stream_disconnected", session_id=session_id)
    except Exception as exc:
        log.exception(
            "voice_stream_error",
            session_id=session_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
