"""
TTS provider factory for vaaniq-voice (LiveKit Agents).

Returns a LiveKit TTS plugin instance for the requested provider.
Providers are loaded lazily to avoid importing SDKs that aren't installed.

All builder functions validate the requested model/voice against a known-good set
and fall back to the provider default with a warning log rather than crashing the
AgentSession with a remote 400/authentication error.
"""

import structlog
from vaaniq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError
from vaaniq.voice.pipeline.context import VoiceCallContext

log = structlog.get_logger()


def create_tts_plugin(context: VoiceCallContext):
    """
    Return a LiveKit TTS plugin configured for the given call context.

    Args:
        context: Fully resolved VoiceCallContext with org_keys and provider settings.

    Returns:
        A livekit.agents.tts.TTS instance ready to attach to an Agent.

    Raises:
        ProviderNotFoundError: If the provider is not supported.
        MissingAPIKeyError: If the org has not configured an API key for the provider.
    """
    provider = context.tts_provider
    org_keys = context.org_keys
    voice_id = context.agent_voice_id
    model = context.tts_model
    speed = context.tts_speed
    language = context.agent_language

    if provider == "cartesia":
        return _build_cartesia(org_keys, voice_id, model, speed, language)
    if provider == "elevenlabs":
        return _build_elevenlabs(org_keys, voice_id, model, speed)
    if provider == "sarvam":
        return _build_sarvam(org_keys, voice_id, language)

    raise ProviderNotFoundError("tts", provider)


# ── Cartesia ──────────────────────────────────────────────────────────────────

_VALID_CARTESIA_MODELS = {"sonic-2", "sonic-english", "sonic-multilingual"}
_CARTESIA_DEFAULT_MODEL = "sonic-2"


def _build_cartesia(
    org_keys: dict,
    voice_id: str | None,
    model: str | None,
    speed: float | None,
    language: str,
):
    from livekit.plugins import cartesia

    api_key = _extract_key(org_keys, "cartesia")
    effective_model = _sanitize_model(
        model, _VALID_CARTESIA_MODELS, _CARTESIA_DEFAULT_MODEL, "cartesia_tts"
    )
    kwargs: dict = {
        "api_key": api_key,
        "voice": voice_id or "a0e99841-438c-4a64-b679-ae501e7d6091",  # Cartesia default
        "model": effective_model,
        "language": language[:2].lower(),  # Cartesia uses "en", "hi", etc.
        "encoding": "pcm_s16le",
        "sample_rate": 24000,
    }
    if speed is not None:
        kwargs["speed"] = speed
    return cartesia.TTS(**kwargs)


# ── ElevenLabs ────────────────────────────────────────────────────────────────

_VALID_ELEVENLABS_MODELS = {
    "eleven_flash_v2_5",
    "eleven_turbo_v2_5",
    "eleven_turbo_v2",
    "eleven_multilingual_v2",
    "eleven_monolingual_v1",
    "eleven_multilingual_v1",
}
_ELEVENLABS_DEFAULT_MODEL = "eleven_flash_v2_5"


def _build_elevenlabs(
    org_keys: dict,
    voice_id: str | None,
    model: str | None,
    speed: float | None,  # noqa: ARG001 — not supported by current ElevenLabs plugin
):
    from livekit.plugins import elevenlabs

    api_key = _extract_key(org_keys, "elevenlabs")
    effective_model = _sanitize_model(
        model, _VALID_ELEVENLABS_MODELS, _ELEVENLABS_DEFAULT_MODEL, "elevenlabs_tts"
    )
    return elevenlabs.TTS(
        api_key=api_key,
        voice_id=voice_id or elevenlabs.DEFAULT_VOICE_ID,
        model=effective_model,
    )


# ── Sarvam AI TTS (Indian languages) ─────────────────────────────────────────

def _build_sarvam(org_keys: dict, voice_id: str | None, language: str):
    from vaaniq.voice.tts.sarvam import SarvamTTS

    api_key = _extract_key(org_keys, "sarvam")
    return SarvamTTS(api_key=api_key, voice=voice_id, language=language)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitize_model(
    model: str | None,
    valid: set[str],
    default: str,
    provider_label: str,
) -> str:
    """
    Return `model` if it is in the valid set, otherwise return `default`.

    Logs a warning when an unrecognised value is replaced so operators can
    find and clean up stale DB values without the call failing silently.
    """
    if not model:
        return default
    if model in valid:
        return model
    log.warning(
        f"{provider_label}_invalid_model_fallback",
        requested=model,
        fallback=default,
    )
    return default


def _extract_key(org_keys: dict, provider: str) -> str:
    value = org_keys.get(provider)
    if not value:
        raise MissingAPIKeyError(provider)
    if isinstance(value, dict):
        value = value.get("api_key", "")
    if not value:
        raise MissingAPIKeyError(provider)
    return str(value)
