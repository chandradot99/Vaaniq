"""
Twilio voice webhook handlers.

Twilio calls these endpoints when calls arrive on our numbers.
Audio is routed through LiveKit SIP — Twilio dials into a LiveKit room
and the LiveKit worker (naaviq-voice.worker) handles the voice pipeline.

Flow:
    1. Twilio receives inbound call on org's number
    2. Twilio hits POST /webhooks/twilio/voice/inbound
    3. naaviq-server creates a LiveKit room (name = session_id)
    4. Returns TwiML: <Dial><Sip>sip:<session_id>@livekit-sip-url</Sip></Dial>
    5. Twilio connects to LiveKit SIP — LiveKit dispatches job to worker
    6. Worker joins room, runs NaaviqVoiceAgent until call ends

Signature verification: X-Twilio-Signature HMAC-SHA1 on every request.
No /v1/ prefix — Twilio controls these URLs.
"""

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from naaviq.server.core.database import get_db
from naaviq.server.webhooks.dependencies import verify_twilio_signature
from naaviq.server.webhooks.service import VoiceWebhookService
from naaviq.voice_server.livekit_helpers import create_livekit_room, livekit_sip_uri

log = structlog.get_logger()

router = APIRouter(prefix="/webhooks/twilio", tags=["twilio"])


# ── Inbound call ──────────────────────────────────────────────────────────────

@router.post("/voice/inbound", dependencies=[Depends(verify_twilio_signature)])
async def voice_inbound(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Twilio hits this when a call arrives on one of our numbers.

    Creates a session and returns TwiML dialling into a LiveKit SIP room.
    """
    session_id = await VoiceWebhookService(db).handle_inbound(CallSid, From, To)
    if session_id is None:
        twiml = _hangup_twiml("Sorry, no agent is configured for this number. Goodbye.")
        return Response(content=twiml, media_type="application/xml")

    await create_livekit_room(session_id)
    sip_uri = livekit_sip_uri(session_id)
    log.info("twilio_inbound_routing", session_id=session_id, sip_uri=sip_uri)
    return Response(content=_sip_dial_twiml(sip_uri), media_type="application/xml")


# ── Outbound call ─────────────────────────────────────────────────────────────

@router.post("/voice/outbound", dependencies=[Depends(verify_twilio_signature)])
async def voice_outbound(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Twilio hits this when an outbound call is answered.
    The session already exists — connect it to the LiveKit room.
    """
    await create_livekit_room(session_id)
    sip_uri = livekit_sip_uri(session_id)
    log.info("twilio_outbound_answered", session_id=session_id, sip_uri=sip_uri)
    return Response(content=_sip_dial_twiml(sip_uri), media_type="application/xml")


# ── Call status callback ──────────────────────────────────────────────────────

@router.post("/voice/status", dependencies=[Depends(verify_twilio_signature)])
async def voice_status(
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
        from naaviq.server.voice.finalization import finalize_voice_session
        background_tasks.add_task(finalize_voice_session, session_id, org_id)
    return Response(content="", status_code=204)


# ── Recording callback ────────────────────────────────────────────────────────

@router.post("/voice/recording", dependencies=[Depends(verify_twilio_signature)])
async def voice_recording(
    CallSid: str = Form(...),
    RecordingUrl: str = Form(...),
    RecordingDuration: str = Form(default="0"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Twilio fires this when a call recording is ready."""
    await VoiceWebhookService(db).handle_recording(CallSid, RecordingUrl, RecordingDuration)
    return Response(content="", status_code=204)


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
