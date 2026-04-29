"""
LiveKit room event webhook handler.

LiveKit fires this on room events (participant joined/left, room closed).
Used for session lifecycle management independent of telephony provider callbacks.

Signature verification:
    LiveKit signs webhook payloads with LIVEKIT_API_SECRET using SHA-256 HMAC.
    Verification is handled inside handle_livekit_room_event().
"""

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from naaviq.server.core.database import get_db

log = structlog.get_logger()

router = APIRouter(prefix="/webhooks/livekit", tags=["livekit"])


@router.post("/room")
async def livekit_room_event(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    LiveKit room event webhook — participant joined/left, room closed.

    LiveKit signs each webhook with LIVEKIT_API_SECRET.
    Signature verification is performed inside handle_livekit_room_event().
    """
    from naaviq.server.voice.livekit_webhooks import handle_livekit_room_event

    body = await request.body()
    auth_header = request.headers.get("Authorization", "")
    await handle_livekit_room_event(body, auth_header, db)
    return Response(content="", status_code=200)
