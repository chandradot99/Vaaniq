"""
Telnyx voice webhook handlers.

Telnyx is a Twilio alternative with lower per-minute costs and native SIP trunking.
It uses TeXML (TwiML-compatible XML) for call control, so the response format
is nearly identical to Twilio.

Flow:
    1. Caller dials Telnyx number
    2. Telnyx hits POST /webhooks/telnyx/voice/inbound
    3. vaaniq-server creates LiveKit room and returns TeXML with <Dial><Sip>
    4. Telnyx connects to LiveKit SIP → worker handles the call

Signature verification:
    Telnyx signs webhooks with Ed25519. The public key is set in the Telnyx
    Mission Control Portal under "API Keys & OAuth" → "Webhook Signing Key".
    Set TELNYX_PUBLIC_KEY in your environment to enable verification.

    Headers: telnyx-signature-ed25519, telnyx-timestamp
    Message signed: {timestamp}|{body}
"""

import base64
import time

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.config import settings
from vaaniq.server.core.database import get_db
from vaaniq.server.webhooks.service import VoiceWebhookService
from vaaniq.voice_server.livekit_helpers import create_livekit_room, livekit_sip_uri

log = structlog.get_logger()

router = APIRouter(prefix="/webhooks/telnyx", tags=["telnyx"])

# Maximum age (seconds) to accept for webhook timestamps (replay protection)
_MAX_TIMESTAMP_AGE = 300


# ── Signature verification dependency ─────────────────────────────────────────

async def verify_telnyx_signature(
    request: Request,
    telnyx_signature_ed25519: str = Header(default=""),
    telnyx_timestamp: str = Header(default=""),
) -> None:
    """
    Verify Telnyx Ed25519 webhook signature.

    Skip verification if TELNYX_PUBLIC_KEY is not configured (dev mode).
    """
    public_key_b64 = getattr(settings, "telnyx_public_key", "")
    if not public_key_b64:
        log.debug("telnyx_signature_verification_skipped", reason="no_public_key_configured")
        return

    if not telnyx_signature_ed25519 or not telnyx_timestamp:
        raise HTTPException(status_code=403, detail="Missing Telnyx signature headers")

    # Replay protection — reject stale timestamps
    try:
        ts = int(telnyx_timestamp)
        if abs(time.time() - ts) > _MAX_TIMESTAMP_AGE:
            raise HTTPException(status_code=403, detail="Telnyx webhook timestamp too old")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid Telnyx timestamp") from exc

    body = await request.body()
    message = f"{telnyx_timestamp}|{body.decode()}".encode()

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        public_key_bytes = base64.b64decode(public_key_b64)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        signature_bytes = base64.b64decode(telnyx_signature_ed25519)
        public_key.verify(signature_bytes, message)
    except Exception as exc:
        log.warning("telnyx_signature_invalid", error=str(exc))
        raise HTTPException(status_code=403, detail="Invalid Telnyx signature") from exc


# ── Inbound call ──────────────────────────────────────────────────────────────

@router.post("/voice/inbound", dependencies=[Depends(verify_telnyx_signature)])
async def voice_inbound(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """
    Telnyx hits this when a call arrives on one of our numbers.

    Parses the Telnyx call payload (JSON), creates a session, and returns
    TeXML dialling into a LiveKit SIP room.
    """
    payload = await request.json()
    data = payload.get("data", {}).get("payload", {})

    call_sid = data.get("call_control_id", "")
    from_number = data.get("from", "")
    to_number = data.get("to", "")

    session_id = await VoiceWebhookService(db).handle_inbound(call_sid, from_number, to_number)
    if session_id is None:
        twiml = _hangup_texml("Sorry, no agent is configured for this number. Goodbye.")
        return Response(content=twiml, media_type="application/xml")

    await create_livekit_room(session_id)
    sip_uri = livekit_sip_uri(session_id)
    log.info("telnyx_inbound_routing", session_id=session_id, sip_uri=sip_uri)
    return Response(content=_sip_dial_texml(sip_uri), media_type="application/xml")


# ── Call status callback ──────────────────────────────────────────────────────

@router.post("/voice/status", dependencies=[Depends(verify_telnyx_signature)])
async def voice_status(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Telnyx fires this on call state transitions (answered, hangup, etc.)."""
    payload = await request.json()
    data = payload.get("data", {}).get("payload", {})

    call_sid = data.get("call_control_id", "")
    event_type = payload.get("data", {}).get("event_type", "")
    duration = str(data.get("billing_secs", 0))

    # Map Telnyx event types to a normalised status
    status_map = {
        "call.hangup": "completed",
        "call.answered": "in-progress",
        "call.initiated": "ringing",
    }
    normalised_status = status_map.get(event_type, "")

    if normalised_status in ("completed",):
        result = await VoiceWebhookService(db).handle_status(call_sid, normalised_status, duration)
        if result is not None:
            session_id, org_id = result
            from vaaniq.server.voice.finalization import finalize_voice_session
            background_tasks.add_task(finalize_voice_session, session_id, org_id)

    return Response(content="", status_code=204)


# ── TeXML helpers (Telnyx-compatible TwiML) ───────────────────────────────────

def _sip_dial_texml(sip_uri: str) -> str:
    """TeXML that connects the call to a LiveKit SIP room."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Dial>"
        f'<Sip>{sip_uri}</Sip>'
        "</Dial>"
        "</Response>"
    )


def _hangup_texml(message: str) -> str:
    """TeXML that speaks a message and hangs up."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Say>{message}</Say>"
        "<Hangup/>"
        "</Response>"
    )
