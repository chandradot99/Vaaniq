"""
Vonage (Nexmo) voice webhook handlers.

Vonage uses a JSON-based call control format called NCCO (Nexmo Call Control Objects)
instead of XML. The answer webhook must return a JSON array of NCCO actions.

Flow:
    1. Caller dials Vonage number
    2. Vonage hits GET /webhooks/vonage/voice/answer
    3. vaaniq-server creates LiveKit room and returns NCCO with connect action
    4. Vonage connects to LiveKit SIP → worker handles the call

Signature verification:
    Vonage signs webhooks using JWT (if configured) or HMAC-SHA256.
    Set VONAGE_SIGNATURE_SECRET in your environment to enable HMAC verification.

NCCO SIP connect format:
    [{"action": "connect", "endpoint": [{"type": "sip", "uri": "sip:..."}]}]

Setup in Vonage Dashboard:
    - Application type: Voice
    - Answer URL: https://your-domain/webhooks/vonage/voice/answer (GET)
    - Event URL:  https://your-domain/webhooks/vonage/voice/event (POST)
"""

import hashlib
import hmac

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.config import settings
from vaaniq.server.core.database import get_db
from vaaniq.server.webhooks.service import VoiceWebhookService
from vaaniq.voice_server.livekit_helpers import create_livekit_room, livekit_sip_uri

log = structlog.get_logger()

router = APIRouter(prefix="/webhooks/vonage", tags=["vonage"])


# ── Signature verification ─────────────────────────────────────────────────────

def _verify_vonage_hmac(request_body: bytes, signature: str) -> bool:
    """
    Verify Vonage HMAC-SHA256 webhook signature.

    Vonage HMAC-SHA256: the signature is an HMAC of the raw request body
    using the application's signature secret.
    """
    secret = getattr(settings, "vonage_signature_secret", "")
    if not secret:
        return True  # skip verification if not configured

    expected = hmac.new(
        secret.encode(),
        request_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


# ── Answer webhook (GET) ──────────────────────────────────────────────────────

@router.get("/voice/answer")
async def voice_answer(
    request: Request,
    from_: str = Query(alias="from", default=""),
    to: str = Query(default=""),
    uuid: str = Query(default=""),
    conversation_uuid: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Vonage calls this (GET) when a call arrives on one of our numbers.

    Returns an NCCO JSON array connecting the call to a LiveKit SIP room.

    Query params from Vonage: from, to, uuid, conversation_uuid
    """
    session_id = await VoiceWebhookService(db).handle_inbound(uuid, from_, to)
    if session_id is None:
        ncco = _hangup_ncco("Sorry, no agent is configured for this number. Goodbye.")
        return Response(content=ncco, media_type="application/json")

    await create_livekit_room(session_id)
    sip_uri = livekit_sip_uri(session_id)
    log.info("vonage_inbound_routing", session_id=session_id, sip_uri=sip_uri)
    return Response(content=_sip_connect_ncco(sip_uri, from_), media_type="application/json")


# ── Event webhook (POST) ──────────────────────────────────────────────────────

@router.post("/voice/event")
async def voice_event(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Vonage fires this on every call state change (ringing, answered, completed).

    Performs finalization when the call is completed.
    """
    # Optional HMAC verification
    body = await request.body()
    signature = request.headers.get("x-nexmo-signature", "")
    if signature and not _verify_vonage_hmac(body, signature):
        raise HTTPException(status_code=403, detail="Invalid Vonage signature")

    try:
        import json
        payload = json.loads(body)
    except Exception:
        return Response(content="", status_code=204)

    call_uuid = payload.get("uuid", "")
    status = payload.get("status", "")
    duration = str(payload.get("duration", 0))

    if status == "completed" and call_uuid:
        result = await VoiceWebhookService(db).handle_status(call_uuid, "completed", duration)
        if result is not None:
            session_id, org_id = result
            from vaaniq.server.voice.finalization import finalize_voice_session
            background_tasks.add_task(finalize_voice_session, session_id, org_id)

    return Response(content="", status_code=204)


# ── NCCO helpers ──────────────────────────────────────────────────────────────

def _sip_connect_ncco(sip_uri: str, from_number: str) -> str:
    """NCCO that connects the call to a LiveKit SIP room."""
    import json

    ncco = [
        {
            "action": "connect",
            "from": from_number or "unknown",
            "timeout": 60,
            "endpoint": [
                {
                    "type": "sip",
                    "uri": sip_uri,
                }
            ],
        }
    ]
    return json.dumps(ncco)


def _hangup_ncco(message: str) -> str:
    """NCCO that speaks a message and ends the call."""
    import json

    ncco = [
        {"action": "talk", "text": message},
    ]
    return json.dumps(ncco)
