"""
Shared LiveKit helpers used by all telephony webhook routers.

Each provider (Twilio, Telnyx, Vonage) follows the same flow:
    1. Receive inbound call webhook
    2. Create a LiveKit room with session_id metadata
    3. Return a dial response pointing to the LiveKit SIP URI

These helpers centralise the room creation and URI construction so that
adding a new telephony provider only requires a new router file.
"""

import json

import structlog

log = structlog.get_logger()


def livekit_sip_uri(session_id: str) -> str:
    """
    Build the LiveKit SIP URI for the given session.

    The SIP domain is derived from LIVEKIT_SIP_DOMAIN (if set) or from
    LIVEKIT_URL. For LiveKit Cloud the pattern is:
        wss://my-project.livekit.cloud → my-project.sip.livekit.cloud

    For self-hosted LiveKit, set LIVEKIT_SIP_DOMAIN explicitly.
    """
    from vaaniq.server.core.config import settings

    sip_domain = getattr(settings, "livekit_sip_domain", "")
    if not sip_domain:
        livekit_url = getattr(settings, "livekit_url", "")
        if livekit_url:
            host = livekit_url.removeprefix("wss://").removeprefix("ws://").split("/")[0]
            if ".livekit.cloud" in host:
                project = host.split(".livekit.cloud")[0]
                sip_domain = f"{project}.sip.livekit.cloud"

    return f"sip:{session_id}@{sip_domain}"


async def create_livekit_room(session_id: str) -> None:
    """
    Pre-create a LiveKit room so the session_id metadata is available
    when the LiveKit worker picks up the dispatched job.

    Room name = session_id. Metadata contains {"session_id": session_id}
    so the worker can load VoiceCallContext without a DB lookup.

    Non-fatal: if room creation fails, LiveKit may auto-create the room
    on SIP connect, but metadata will be empty and the worker will fall
    back to phone-number lookup.
    """
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
        log.warning("livekit_room_create_failed", session_id=session_id, error=str(exc))
