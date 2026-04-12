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
    if provider == "azure":
        return _build_azure(org_keys, voice_id, language)
    if provider == "deepgram":
        return _build_deepgram(org_keys, voice_id, model)
    if provider == "sarvam":
        return _build_sarvam(org_keys, voice_id, language)
    if provider == "openai":
        return _build_openai(org_keys, voice_id, model, speed)

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


# ── Azure Speech ──────────────────────────────────────────────────────────────

def _build_azure(org_keys: dict, voice_id: str | None, language: str):
    from livekit.plugins import azure

    creds = org_keys.get("azure", {})
    if isinstance(creds, str):
        speech_key = creds
        region = "eastus"
    else:
        speech_key = creds.get("api_key") or creds.get("speech_key", "")
        region = creds.get("region", "eastus")

    if not speech_key:
        raise MissingAPIKeyError("azure")

    # Azure voice IDs follow the pattern: <locale>-<VoiceName>Neural
    # e.g. "hi-IN-SwaraNeural", "ta-IN-PallaviNeural"
    return azure.TTS(
        speech_key=speech_key,
        speech_region=region,
        voice=voice_id or _azure_default_voice(language),
    )


def _azure_default_voice(language: str) -> str:
    """Return a sensible Azure default voice for the given BCP-47 language code."""
    defaults = {
        "hi-IN": "hi-IN-SwaraNeural",
        "ta-IN": "ta-IN-PallaviNeural",
        "te-IN": "te-IN-ShrutiNeural",
        "mr-IN": "mr-IN-AarohiNeural",
        "bn-IN": "bn-IN-TanishaaNeural",
        "gu-IN": "gu-IN-DhwaniNeural",
        "kn-IN": "kn-IN-SapnaNeural",
        "ml-IN": "ml-IN-SobhanaNeural",
        "pa-IN": "pa-IN-OjasvNeural",
        "en-IN": "en-IN-NeerjaNeural",
        "en-US": "en-US-AriaNeural",
        "en-GB": "en-GB-SoniaNeural",
    }
    return defaults.get(language, "en-US-AriaNeural")


# ── Deepgram TTS ──────────────────────────────────────────────────────────────

# Deepgram TTS voices — the model field is the voice ID (aura-2-* prefix).
# Rather than maintaining an exhaustive list, we validate the naming convention.
_DEEPGRAM_TTS_DEFAULT = "aura-2-en-us"


def _build_deepgram(org_keys: dict, voice_id: str | None, model: str | None):
    from livekit.plugins import deepgram

    api_key = _extract_key(org_keys, "deepgram")
    # voice_id takes priority; model is the fallback (both map to the same field)
    requested = voice_id or model
    effective = _sanitize_deepgram_tts_voice(requested)
    return deepgram.TTS(api_key=api_key, model=effective)


def _sanitize_deepgram_tts_voice(voice: str | None) -> str:
    """
    Deepgram Aura voices follow the pattern 'aura-2-<name>-<locale>'.
    Accept any value matching this prefix; reject (and default) anything else.
    """
    if voice and voice.startswith("aura-"):
        return voice
    if voice:
        log.warning(
            "deepgram_tts_invalid_voice_fallback",
            requested=voice,
            fallback=_DEEPGRAM_TTS_DEFAULT,
        )
    return _DEEPGRAM_TTS_DEFAULT


# ── Sarvam AI TTS (Indian languages) ─────────────────────────────────────────

def _build_sarvam(org_keys: dict, voice_id: str | None, language: str):
    from vaaniq.voice.tts.sarvam import SarvamTTS

    api_key = _extract_key(org_keys, "sarvam")
    return SarvamTTS(api_key=api_key, voice=voice_id, language=language)


# ── OpenAI TTS ────────────────────────────────────────────────────────────────

_VALID_OPENAI_TTS_MODELS = {"tts-1", "tts-1-hd", "gpt-4o-mini-tts"}
_OPENAI_TTS_DEFAULT_MODEL = "tts-1"

_VALID_OPENAI_TTS_VOICES = {
    "alloy", "echo", "fable", "onyx", "nova", "shimmer",
    "ash", "ballad", "coral", "sage", "verse",
}
_OPENAI_TTS_DEFAULT_VOICE = "alloy"


def _build_openai(
    org_keys: dict,
    voice_id: str | None,
    model: str | None,
    speed: float | None,
):
    from livekit.plugins import openai as lk_openai

    api_key = _extract_key(org_keys, "openai")
    effective_model = _sanitize_model(
        model, _VALID_OPENAI_TTS_MODELS, _OPENAI_TTS_DEFAULT_MODEL, "openai_tts"
    )
    effective_voice = _sanitize_model(
        voice_id, _VALID_OPENAI_TTS_VOICES, _OPENAI_TTS_DEFAULT_VOICE, "openai_tts_voice"
    )
    kwargs: dict = {
        "api_key": api_key,
        "voice": effective_voice,
        "model": effective_model,
    }
    if speed is not None:
        kwargs["speed"] = speed
    return lk_openai.TTS(**kwargs)


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
