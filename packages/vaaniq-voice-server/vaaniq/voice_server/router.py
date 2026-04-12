"""
Twilio voice webhook handlers.

Twilio calls these endpoints when calls arrive on our numbers.
Audio is routed through LiveKit SIP — Twilio dials into a LiveKit room
and the LiveKit worker (vaaniq-voice.worker) handles the voice pipeline.

Flow:
    1. Twilio receives inbound call on org's number
    2. Twilio hits POST /webhooks/twilio/voice/inbound
    3. vaaniq-server creates a LiveKit room (name = session_id)
    4. Returns TwiML: <Dial><Sip>sip:<session_id>@livekit-sip-url</Sip></Dial>
    5. Twilio connects to LiveKit SIP — LiveKit dispatches job to worker
    6. Worker joins room, runs VaaniqVoiceAgent until call ends

No /v1/ prefix — Twilio controls these URLs.
"""

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.database import get_db
from vaaniq.server.webhooks.dependencies import verify_twilio_signature
from vaaniq.server.webhooks.service import VoiceWebhookService

log = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _livekit_sip_uri(session_id: str) -> str:
    """
    Build the LiveKit SIP URI for the given session.

    LiveKit SIP inbound trunk address is configured in the LiveKit dashboard.
    The username part (session_id) is passed as room metadata via SIP headers.
    """
    from vaaniq.server.core.config import settings

    # Format: sip:<room-name>@<livekit-sip-domain>
    # LiveKit SIP domain: <project>.sip.livekit.cloud (cloud) or sip.<host> (self-hosted)
    sip_domain = getattr(settings, "livekit_sip_domain", "")
    if not sip_domain:
        # Derive from LIVEKIT_URL: wss://project.livekit.cloud → project.sip.livekit.cloud
        livekit_url = getattr(settings, "livekit_url", "")
        if livekit_url:
            host = livekit_url.removeprefix("wss://").removeprefix("ws://").split("/")[0]
            # e.g. "my-project.livekit.cloud" → "my-project.sip.livekit.cloud"
            if ".livekit.cloud" in host:
                project = host.split(".livekit.cloud")[0]
                sip_domain = f"{project}.sip.livekit.cloud"
    return f"sip:{session_id}@{sip_domain}"


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

    Creates a session and returns TwiML dialling into a LiveKit SIP room.
    The LiveKit worker picks up the job and runs the voice agent.
    """
    session_id = await VoiceWebhookService(db).handle_inbound(CallSid, From, To)
    if session_id is None:
        twiml = _hangup_twiml("Sorry, no agent is configured for this number. Goodbye.")
        return Response(content=twiml, media_type="application/xml")

    # Create the LiveKit room upfront so metadata is ready when the worker joins.
    await _create_livekit_room(session_id)

    sip_uri = _livekit_sip_uri(session_id)
    twiml = _sip_dial_twiml(sip_uri)
    log.info("voice_inbound_routing", session_id=session_id, sip_uri=sip_uri)
    return Response(content=twiml, media_type="application/xml")


# ── Outbound call ─────────────────────────────────────────────────────────────

@router.post("/twilio/voice/outbound", dependencies=[Depends(verify_twilio_signature)])
async def twilio_voice_outbound(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Twilio hits this when an outbound call is answered.
    The session already exists — connect it to the LiveKit room.
    """
    sip_uri = _livekit_sip_uri(session_id)
    log.info("voice_outbound_answered", session_id=session_id)
    return Response(content=_sip_dial_twiml(sip_uri), media_type="application/xml")


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


# ── LiveKit room webhook ───────────────────────────────────────────────────────

@router.post("/livekit/room")
async def livekit_room_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    LiveKit room event webhook — participant joined/left, room closed.

    Used for session lifecycle management when LiveKit signals room closure
    independent of Twilio's status callbacks (e.g. WebRTC disconnects).
    """
    # LiveKit signs webhooks with LIVEKIT_API_SECRET
    # Signature verification is done here before processing
    from vaaniq.server.voice.livekit_webhooks import handle_livekit_room_event
    body = await request.body()
    auth_header = request.headers.get("Authorization", "")
    await handle_livekit_room_event(body, auth_header, db)
    return Response(content="", status_code=200)


# ── TwiML helpers ─────────────────────────────────────────────────────────────

def _sip_dial_twiml(sip_uri: str) -> str:
    """TwiML that connects the call to a LiveKit SIP room."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Dial>"
        f'<Sip>{sip_uri}</Sip>'
        "</Dial>"
        "</Response>"
    )


def _hangup_twiml(message: str) -> str:
    """TwiML that speaks a message and hangs up."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Say>{message}</Say>"
        "<Hangup/>"
        "</Response>"
    )


# ── LiveKit room creation ──────────────────────────────────────────────────────

async def _create_livekit_room(session_id: str) -> None:
    """
    Pre-create the LiveKit room so metadata (session_id) is available
    when the worker picks up the job.

    The room name = session_id so the worker can look it up directly.
    """
    import json

    try:
        from livekit.api import CreateRoomRequest, LiveKitAPI
        from vaaniq.server.core.config import settings

        livekit_url = getattr(settings, "livekit_url", "")
        livekit_api_key = getattr(settings, "livekit_api_key", "")
        livekit_api_secret = getattr(settings, "livekit_api_secret", "")

        if not all([livekit_url, livekit_api_key, livekit_api_secret]):
            log.warning("livekit_room_create_skipped", reason="credentials_not_configured")
            return

        async with LiveKitAPI(
            url=livekit_url,
            api_key=livekit_api_key,
            api_secret=livekit_api_secret,
        ) as lk:
            await lk.room.create_room(
                CreateRoomRequest(
                    name=session_id,
                    metadata=json.dumps({"session_id": session_id}),
                    empty_timeout=300,   # 5 min — close room if no participants join
                    max_participants=10,
                )
            )
        log.info("livekit_room_created", session_id=session_id)
    except Exception as exc:
        # Non-fatal — LiveKit may auto-create the room on SIP connect
        log.warning("livekit_room_create_failed", session_id=session_id, error=str(exc))
