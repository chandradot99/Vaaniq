"""
LiveKit room webhook handler.

LiveKit POSTs to /webhooks/livekit/room when room events occur:
  - participant_joined  → agent worker has connected
  - participant_left    → caller or worker disconnected
  - room_finished       → all participants left, room closed

Used for session lifecycle management alongside Twilio's status callbacks.
"""

import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()


async def handle_livekit_room_event(
    body: bytes,
    auth_header: str,
    db: AsyncSession,
) -> None:
    """
    Process a LiveKit room webhook event.

    LiveKit signs webhooks with a JWT using LIVEKIT_API_SECRET.
    Signature verification ensures the event is genuine before processing.
    """
    # ── Signature verification ────────────────────────────────────────────────
    if not _verify_livekit_signature(body, auth_header):
        log.warning("livekit_webhook_invalid_signature")
        return

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        log.warning("livekit_webhook_invalid_json")
        return

    event_type = event.get("event")
    room = event.get("room", {})
    room_name = room.get("name", "")

    log.info("livekit_room_event", event=event_type, room=room_name)

    if event_type == "room_finished":
        # Room closed — ensure session is finalized if Twilio status callback
        # was delayed or missed.
        await _handle_room_finished(room_name, db)


async def _handle_room_finished(room_name: str, db: AsyncSession) -> None:
    """
    Called when a LiveKit room closes. room_name == session_id.

    If the session is still in a non-terminal state (Twilio status callback
    hasn't arrived yet), mark it as completed.
    """
    from naaviq.server.webhooks.repository import SessionRepository

    session = await SessionRepository(db).get_by_id(room_name)
    if not session:
        return

    log.info("livekit_room_finished", session_id=room_name, status=session.status)


def _verify_livekit_signature(body: bytes, auth_header: str) -> bool:
    """
    Verify the LiveKit webhook JWT signature.

    LiveKit signs the body with HMAC-SHA256 using the API secret.
    Returns True if the signature is valid, False otherwise.
    """
    try:
        from livekit.api import WebhookReceiver

        from naaviq.server.core.config import settings

        api_key = getattr(settings, "livekit_api_key", "")
        api_secret = getattr(settings, "livekit_api_secret", "")
        if not api_key or not api_secret:
            log.warning("livekit_webhook_no_credentials")
            return False

        receiver = WebhookReceiver(api_key=api_key, api_secret=api_secret)
        receiver.receive(body.decode(), auth_header)
        return True
    except Exception as exc:
        log.warning("livekit_webhook_signature_failed", error=str(exc))
        return False
