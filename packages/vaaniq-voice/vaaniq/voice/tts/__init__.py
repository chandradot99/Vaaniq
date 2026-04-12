"""
TTS provider factory for vaaniq-voice (LiveKit Agents).

Returns a LiveKit TTS plugin instance for the requested provider.
Providers are loaded lazily to avoid importing SDKs that aren't installed.
"""

from vaaniq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError
from vaaniq.voice.pipeline.context import VoiceCallContext


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

def _build_cartesia(
    org_keys: dict,
    voice_id: str | None,
    model: str | None,
    speed: float | None,
    language: str,
):
    from livekit.plugins import cartesia

    api_key = _extract_key(org_keys, "cartesia")
    kwargs: dict = {
        "api_key": api_key,
        "voice": voice_id or "a0e99841-438c-4a64-b679-ae501e7d6091",  # Cartesia default
        "model": model or "sonic-2",
        "language": language[:2].lower(),  # Cartesia uses "en", "hi", etc.
        "encoding": "pcm_s16le",
        "sample_rate": 24000,
    }
    if speed is not None:
        kwargs["speed"] = speed
    return cartesia.TTS(**kwargs)


# ── ElevenLabs ────────────────────────────────────────────────────────────────

def _build_elevenlabs(
    org_keys: dict,
    voice_id: str | None,
    model: str | None,
    speed: float | None,  # noqa: ARG001 — not supported by current ElevenLabs plugin
):
    from livekit.plugins import elevenlabs

    api_key = _extract_key(org_keys, "elevenlabs")
    return elevenlabs.TTS(
        api_key=api_key,
        voice_id=voice_id or elevenlabs.DEFAULT_VOICE_ID,
        model=model or "eleven_flash_v2_5",
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

def _build_deepgram(org_keys: dict, voice_id: str | None, model: str | None):
    from livekit.plugins import deepgram

    api_key = _extract_key(org_keys, "deepgram")
    return deepgram.TTS(
        api_key=api_key,
        model=voice_id or model or "aura-2-en-us",
    )


# ── Sarvam AI TTS (Indian languages) ─────────────────────────────────────────

def _build_sarvam(org_keys: dict, voice_id: str | None, language: str):
    from vaaniq.voice.tts.sarvam import SarvamTTS

    api_key = _extract_key(org_keys, "sarvam")
    return SarvamTTS(api_key=api_key, voice=voice_id, language=language)


# ── OpenAI TTS ────────────────────────────────────────────────────────────────

def _build_openai(
    org_keys: dict,
    voice_id: str | None,
    model: str | None,
    speed: float | None,
):
    from livekit.plugins import openai as lk_openai

    api_key = _extract_key(org_keys, "openai")
    kwargs: dict = {
        "api_key": api_key,
        "voice": voice_id or "alloy",
        "model": model or "tts-1",
    }
    if speed is not None:
        kwargs["speed"] = speed
    return lk_openai.TTS(**kwargs)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_key(org_keys: dict, provider: str) -> str:
    value = org_keys.get(provider)
    if not value:
        raise MissingAPIKeyError(provider)
    if isinstance(value, dict):
        value = value.get("api_key", "")
    if not value:
        raise MissingAPIKeyError(provider)
    return str(value)
