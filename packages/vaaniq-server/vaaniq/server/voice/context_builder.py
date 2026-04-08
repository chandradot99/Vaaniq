"""
VoiceContextBuilder — resolves everything the Pipecat pipeline needs before audio starts.

Called once per WebSocket connection, right after Twilio completes the Media Streams
handshake. The handshake sends two JSON messages before any audio:

  1. {"event": "connected", "protocol": "Call", "version": "1.0.0"}
  2. {"event": "start", "streamSid": "MZ...", "start": {"callSid": "CA...", "accountSid": "AC...", ...}}

We read those two messages to get the stream_sid, then load everything from the DB
and return a fully populated VoiceCallContext for the pipeline builder.
"""

import json

import structlog
from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.admin import platform_cache
from vaaniq.server.agents.repository import AgentRepository
from vaaniq.server.integrations.repository import IntegrationRepository
from vaaniq.server.integrations.service import PostgresCredentialStore
from vaaniq.server.voice.exceptions import (
    AgentNotConfigured,
    SessionNotFound,
    TwilioHandshakeError,
)
from vaaniq.server.voice.repository import PhoneNumberRepository
from vaaniq.server.webhooks.repository import SessionRepository
from vaaniq.voice.pipeline.context import VoiceCallContext

log = structlog.get_logger()

# Provider preference order — first one found in the org's integrations wins.
# These are the provider names as stored in the integrations table.
_STT_PREFERENCE = ["deepgram", "assemblyai"]
_TTS_PREFERENCE = ["cartesia", "deepgram", "elevenlabs", "azure"]


async def _read_twilio_handshake(websocket: WebSocket) -> tuple[str, str]:
    """
    Read the two Twilio Media Streams handshake messages and return
    (stream_sid, call_sid).

    Twilio always sends "connected" then "start" before any audio frames.
    We time out after 10 seconds — if no start message arrives, the call
    is treated as a failed connection.
    """
    stream_sid: str = ""
    call_sid: str = ""

    # Read up to 5 messages to find "start" (in practice it's always msg #2)
    for _ in range(5):
        try:
            raw = await websocket.receive_text()
        except Exception as exc:
            raise TwilioHandshakeError(f"WebSocket closed during handshake: {exc}") from exc

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        event = msg.get("event")

        if event == "connected":
            continue  # expected first message — nothing to extract

        if event == "start":
            stream_sid = msg.get("streamSid", "")
            start_data = msg.get("start", {})
            call_sid = start_data.get("callSid", "")
            break

    if not stream_sid:
        raise TwilioHandshakeError("Never received Twilio 'start' event — cannot build pipeline context.")

    return stream_sid, call_sid


def _resolve_provider(category: str, providers_by_category: dict[str, list[str]], preference: list[str]) -> str:
    """
    Pick the best available provider for a category based on preference order.
    Falls back to the first item in preference if nothing is configured.
    """
    available = providers_by_category.get(category, [])
    for preferred in preference:
        if preferred in available:
            return preferred
    # No BYOK integration for this category — return default (first in preference)
    return preference[0]


async def build_voice_context(
    session_id: str,
    websocket: WebSocket,
    db: AsyncSession,
) -> VoiceCallContext:
    """
    Full context resolution for a single voice call.

    1. Read Twilio handshake to get stream_sid + call_sid.
    2. Load session from DB (validates it exists and is for voice).
    3. Load agent (graph_config, language, voice_id).
    4. Decrypt all org integrations → build org_keys.
    5. Resolve STT/TTS providers from org's connected integrations.
    6. Build and return VoiceCallContext.
    """
    # ── Step 1: Twilio handshake ──────────────────────────────────────────────
    try:
        stream_sid, handshake_call_sid = await _read_twilio_handshake(websocket)
    except Exception as exc:
        log.error(
            "voice_handshake_failed",
            session_id=session_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise

    log.info("voice_handshake_complete", session_id=session_id, stream_sid=stream_sid)

    # ── Step 2: Load session ──────────────────────────────────────────────────
    session = await SessionRepository(db).get_by_id(session_id)
    if not session:
        raise SessionNotFound(session_id)

    meta = session.meta or {}
    call_sid = meta.get("call_sid", handshake_call_sid)
    from_number = meta.get("from", session.user_id)
    to_number = meta.get("to", "")

    log.info(
        "voice_context_loading",
        session_id=session_id,
        org_id=session.org_id,
        agent_id=session.agent_id,
        call_sid=call_sid,
    )

    # ── Step 3: Load agent ────────────────────────────────────────────────────
    agent = await AgentRepository(db).get_by_id(str(session.agent_id))
    if not agent:
        raise SessionNotFound(f"Agent {session.agent_id} not found")

    if not agent.graph_config:
        raise AgentNotConfigured(str(agent.id))

    # Build initial messages list (system prompt as OpenAI message format)
    initial_messages = []
    if agent.system_prompt:
        initial_messages = [{"role": "system", "content": agent.system_prompt}]

    # ── Step 4: Load org integrations + decrypt ───────────────────────────────
    integrations = await IntegrationRepository(db).list_by_org(str(session.org_id))

    # Group by category so we know what the org has configured
    providers_by_category: dict[str, list[str]] = {}
    for integration in integrations:
        providers_by_category.setdefault(integration.category, []).append(integration.provider)

    # Decrypt all credentials → org_keys dict (provider → decrypted value)
    org_keys = await PostgresCredentialStore(db).get_org_keys(str(session.org_id))

    # Add platform Twilio credentials as fallback if org hasn't added their own
    if "twilio" not in org_keys:
        platform_twilio = platform_cache.get_provider_config("twilio")
        if platform_twilio and platform_twilio.get("auth_token"):
            org_keys["twilio"] = platform_twilio

    # Add platform STT/TTS keys as fallback so orgs can call without BYOK
    for stt in _STT_PREFERENCE:
        if stt not in org_keys:
            platform_stt = platform_cache.get_provider_config(stt)
            if platform_stt and platform_stt.get("api_key"):
                org_keys[stt] = platform_stt["api_key"]

    for tts in _TTS_PREFERENCE:
        if tts not in org_keys:
            platform_tts = platform_cache.get_provider_config(tts)
            if platform_tts and platform_tts.get("api_key"):
                org_keys[tts] = platform_tts["api_key"]

    # ── Step 5: Resolve Twilio credentials ───────────────────────────────────
    twilio_creds = org_keys.get("twilio", {})
    if isinstance(twilio_creds, dict):
        twilio_account_sid = twilio_creds.get("account_sid", "")
        twilio_auth_token_val = twilio_creds.get("auth_token", "")
    else:
        twilio_account_sid = ""
        twilio_auth_token_val = ""

    # ── Step 6: Look up the phone number record for its voice_config ─────────
    # For inbound: to_number is the org's Twilio number (the dialled number)
    # For outbound: from_number is the org's Twilio number (the calling number)
    direction = meta.get("direction", "inbound")
    org_number = from_number if direction == "outbound" else to_number
    phone_number_record = await PhoneNumberRepository(db).get_by_number(org_number) if org_number else None
    vc = (phone_number_record.voice_config if phone_number_record else None) or {}

    # ── Step 7: Resolve STT / TTS from pipeline voice_config or auto-detect ─
    stt_provider = vc.get("stt_provider") or _resolve_provider("stt", providers_by_category, _STT_PREFERENCE)
    tts_provider = vc.get("tts_provider") or _resolve_provider("tts", providers_by_category, _TTS_PREFERENCE)
    stt_model = vc.get("stt_model")       # None = provider default
    tts_model = vc.get("tts_model")       # None = provider default
    tts_speed = vc.get("tts_speed")       # None = provider default
    # voice_config.language overrides agent.language for this call
    agent_language_resolved = vc.get("language") or agent.language or "en-US"
    # voice_config.tts_voice_id overrides agent.voice_id
    agent_voice_id_resolved = vc.get("tts_voice_id") or agent.voice_id

    log.info(
        "voice_context_resolved",
        session_id=session_id,
        stt_provider=stt_provider,
        tts_provider=tts_provider,
        stream_sid=stream_sid,
    )

    return VoiceCallContext(
        session_id=session_id,
        org_id=str(session.org_id),
        agent_id=str(session.agent_id),
        call_sid=call_sid,
        stream_sid=stream_sid,
        twilio_account_sid=twilio_account_sid,
        twilio_auth_token=twilio_auth_token_val,
        from_number=from_number,
        to_number=to_number,
        agent_language=agent_language_resolved,
        graph_config=agent.graph_config,
        graph_version=agent.graph_version or 1,
        initial_messages=initial_messages,
        org_keys=org_keys,
        stt_provider=stt_provider,
        stt_model=stt_model,
        tts_provider=tts_provider,
        tts_model=tts_model,
        tts_speed=tts_speed,
        agent_voice_id=agent_voice_id_resolved,
        direction=direction,
    )
