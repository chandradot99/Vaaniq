"""
Twilio webhook handlers.
No /v1/ prefix — Twilio controls these URLs and cannot be versioned.
Sprint 1: inbound call -> ElevenLabs hosted agent -> session logged in DB.
"""
from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.database import get_db
from vaaniq.server.webhooks.service import TwilioService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/twilio/inbound")
async def twilio_inbound(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    twiml = await TwilioService(db).handle_inbound(CallSid, From, To)
    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/status")
async def twilio_status(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: str = Form(default="0"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await TwilioService(db).handle_status(CallSid, CallStatus, CallDuration)
    return Response(content="", status_code=204)
