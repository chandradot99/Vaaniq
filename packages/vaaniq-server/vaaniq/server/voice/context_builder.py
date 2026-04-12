"""
VoiceContextBuilder — resolves everything the voice agent needs before audio starts.

Called once per incoming call by the LiveKit worker, after the room is created
and the job is dispatched. Loads all required config from the DB and returns
a fully populated VoiceCallContext for the agent.

Resolution order for STT/TTS:
  1. phone_number.voice_config — per-pipeline override
  2. Org BYOK integrations — auto-detect from configured providers
  3. Platform defaults — fallback to platform_cache keys
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.admin import platform_cache
from vaaniq.server.agents.repository import AgentRepository
from vaaniq.server.integrations.repository import IntegrationRepository
from vaaniq.server.integrations.service import PostgresCredentialStore
from vaaniq.server.voice.exceptions import (
    AgentNotConfigured,
    SessionNotFound,
)
from vaaniq.server.voice.repository import PhoneNumberRepository
from vaaniq.server.webhooks.repository import SessionRepository
from vaaniq.voice.pipeline.context import VoiceCallContext

log = structlog.get_logger()

# Provider preference order — first one found in the org's integrations wins.
_STT_PREFERENCE = ["deepgram", "assemblyai", "sarvam"]
_TTS_PREFERENCE = ["cartesia", "deepgram", "elevenlabs", "azure", "sarvam"]


def _resolve_provider(category: str, providers_by_category: dict[str, list[str]], preference: list[str]) -> str:
    """
    Pick the best available provider for a category based on preference order.
    Falls back to the first item in preference if nothing is configured.
    """
    available = providers_by_category.get(category, [])
    for preferred in preference:
        if preferred in available:
            return preferred
    return preference[0]


async def build_voice_context(
    session_id: str,
    db: AsyncSession,
) -> VoiceCallContext:
    """
    Full context resolution for a single voice call.

    1. Load session from DB (validates it exists and is for voice).
    2. Load agent (graph_config, language, voice_id).
    3. Decrypt all org integrations → build org_keys.
    4. Resolve STT/TTS providers from org's connected integrations.
    5. Build and return VoiceCallContext.

    Args:
        session_id: UUID of the session created by the inbound webhook.
        db:         Async database session.
    """
    # ── Step 1: Load session ──────────────────────────────────────────────────
    session = await SessionRepository(db).get_by_id(session_id)
    if not session:
        raise SessionNotFound(session_id)

    meta = session.meta or {}
    call_sid = meta.get("call_sid", "")
    from_number = meta.get("from", session.user_id)
    to_number = meta.get("to", "")
    direction = meta.get("direction", "inbound")

    log.info(
        "voice_context_loading",
        session_id=session_id,
        org_id=session.org_id,
        agent_id=session.agent_id,
        call_sid=call_sid,
    )

    # ── Step 2: Load agent ────────────────────────────────────────────────────
    agent = await AgentRepository(db).get_by_id(str(session.agent_id))
    if not agent:
        raise SessionNotFound(f"Agent {session.agent_id} not found")

    if not agent.graph_config:
        raise AgentNotConfigured(str(agent.id))

    initial_messages = []
    if agent.system_prompt:
        initial_messages = [{"role": "system", "content": agent.system_prompt}]

    # ── Step 3: Load org integrations + decrypt ───────────────────────────────
    integrations = await IntegrationRepository(db).list_by_org(str(session.org_id))

    providers_by_category: dict[str, list[str]] = {}
    for integration in integrations:
        providers_by_category.setdefault(integration.category, []).append(integration.provider)

    org_keys = await PostgresCredentialStore(db).get_org_keys(str(session.org_id))

    # Platform fallbacks — let orgs call without BYOK while evaluating
    if "twilio" not in org_keys:
        platform_twilio = platform_cache.get_provider_config("twilio")
        if platform_twilio and platform_twilio.get("auth_token"):
            org_keys["twilio"] = platform_twilio

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

    # ── Step 4: Resolve Twilio credentials ───────────────────────────────────
    twilio_creds = org_keys.get("twilio", {})
    if isinstance(twilio_creds, dict):
        twilio_account_sid = twilio_creds.get("account_sid", "")
        twilio_auth_token_val = twilio_creds.get("auth_token", "")
    else:
        twilio_account_sid = ""
        twilio_auth_token_val = ""

    # ── Step 5: Look up phone number voice_config ─────────────────────────────
    org_number = from_number if direction == "outbound" else to_number
    phone_number_record = await PhoneNumberRepository(db).get_by_number(org_number) if org_number else None
    vc = (phone_number_record.voice_config if phone_number_record else None) or {}

    # ── Step 6: Resolve STT / TTS ─────────────────────────────────────────────
    stt_provider = vc.get("stt_provider") or _resolve_provider("stt", providers_by_category, _STT_PREFERENCE)
    tts_provider = vc.get("tts_provider") or _resolve_provider("tts", providers_by_category, _TTS_PREFERENCE)
    stt_model = vc.get("stt_model")
    tts_model = vc.get("tts_model")
    tts_speed = vc.get("tts_speed")
    agent_language = vc.get("language") or agent.language or "en-US"
    agent_voice_id = vc.get("tts_voice_id") or agent.voice_id

    log.info(
        "voice_context_resolved",
        session_id=session_id,
        stt_provider=stt_provider,
        stt_model=stt_model,
        tts_provider=tts_provider,
        tts_model=tts_model,
        language=agent_language,
    )

    return VoiceCallContext(
        session_id=session_id,
        org_id=str(session.org_id),
        agent_id=str(session.agent_id),
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
        agent_language=agent_language,
        graph_config=agent.graph_config,
        graph_version=agent.graph_version or 1,
        initial_messages=initial_messages,
        org_keys=org_keys,
        stt_provider=stt_provider,
        stt_model=stt_model,
        tts_provider=tts_provider,
        tts_model=tts_model,
        tts_speed=tts_speed,
        agent_voice_id=agent_voice_id,
        direction=direction,
        twilio_account_sid=twilio_account_sid,
        twilio_auth_token=twilio_auth_token_val,
    )
