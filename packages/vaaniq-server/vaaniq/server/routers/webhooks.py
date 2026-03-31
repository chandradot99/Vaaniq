"""
Twilio webhook handlers.
No /v1/ prefix — Twilio controls these URLs and cannot be versioned.
Sprint 1: inbound call -> ElevenLabs hosted agent -> session logged in DB.
"""
import structlog
from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from vaaniq.server.core.database import get_db
from vaaniq.server.models.agent import Agent
from vaaniq.server.models.session import Session

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = structlog.get_logger()


@router.post("/twilio/inbound")
async def twilio_inbound(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Twilio calls this when an inbound call arrives on a Vaaniq number.
    1. Look up which agent owns this number (simplified: use first active agent for Sprint 1).
    2. Return TwiML that connects the call to the ElevenLabs Conversational AI widget.
    3. Log a pending session.
    """
    log.info("twilio_inbound", call_sid=CallSid, from_number=From, to_number=To)

    # Sprint 1: find any active agent — in Sprint 2 we'll look up by phone number
    result = await db.execute(select(Agent).where(Agent.deleted_at.is_(None)).limit(1))
    agent = result.scalar_one_or_none()

    if not agent:
        twiml = "<Response><Say>No agent configured. Goodbye.</Say><Hangup/></Response>"
        return Response(content=twiml, media_type="application/xml")

    # Log session start
    session = Session(
        id=CallSid,
        org_id=agent.org_id,
        agent_id=agent.id,
        channel="voice",
        user_id=From,
    )
    db.add(session)
    await db.commit()

    # Return TwiML to connect to ElevenLabs Conversational AI
    # The agent's voice_id is the ElevenLabs agent ID
    elevenlabs_agent_id = agent.voice_id or ""
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://api.elevenlabs.io/v1/convai/twilio?agent_id={elevenlabs_agent_id}" />
  </Connect>
</Response>"""

    log.info("call_connected_to_elevenlabs", call_sid=CallSid, agent_id=agent.id, org_id=agent.org_id)
    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/status")
async def twilio_status(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: str = Form(default="0"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Twilio calls this when a call ends. Update session with duration."""
    log.info("twilio_status", call_sid=CallSid, status=CallStatus, duration=CallDuration)

    result = await db.execute(select(Session).where(Session.id == CallSid))
    session = result.scalar_one_or_none()
    if session:
        try:
            session.duration_seconds = int(CallDuration)
        except ValueError:
            pass
        await db.commit()

    return Response(content="", status_code=204)
