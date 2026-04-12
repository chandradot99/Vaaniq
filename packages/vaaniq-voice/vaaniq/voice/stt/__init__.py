"""
STT provider factory for vaaniq-voice (LiveKit Agents).

Returns a LiveKit STT plugin instance for the requested provider.
Providers are loaded lazily to avoid importing SDKs that aren't installed.
"""

from vaaniq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError
from vaaniq.voice.pipeline.context import VoiceCallContext


def create_stt_plugin(context: VoiceCallContext):
    """
    Return a LiveKit STT plugin configured for the given call context.

    Args:
        context: Fully resolved VoiceCallContext with org_keys and provider settings.

    Returns:
        A livekit.agents.stt.STT instance ready to attach to an Agent.

    Raises:
        ProviderNotFoundError: If the provider is not supported.
        MissingAPIKeyError: If the org has not configured an API key for the provider.
    """
    provider = context.stt_provider
    org_keys = context.org_keys
    language = context.agent_language
    model = context.stt_model

    if provider == "deepgram":
        return _build_deepgram(org_keys, language, model)
    if provider == "sarvam":
        return _build_sarvam(org_keys, language)
    if provider == "assemblyai":
        return _build_assemblyai(org_keys, language)
    if provider == "openai":
        return _build_openai(org_keys, language, model)
    if provider == "azure":
        return _build_azure_stt(org_keys, language)

    raise ProviderNotFoundError("stt", provider)


# ── Deepgram ──────────────────────────────────────────────────────────────────

# Models accepted by the Deepgram streaming API. Any value not in this set
# (e.g. "nova-3-phonecall" which was briefly shown in the UI but never existed)
# falls back to the default to prevent a 400 WebSocket handshake error.
_VALID_DEEPGRAM_MODELS = {
    "nova-3",
    "nova-2",
    "nova-2-phonecall",
    "nova-2-finance",
    "nova-2-general",
    "nova-2-meeting",
    "nova-2-medical",
    "nova-2-conversationalai",
    "enhanced",
    "base",
}
_DEEPGRAM_DEFAULT_MODEL = "nova-3"


def _build_deepgram(org_keys: dict, language: str, model: str | None):
    import structlog
    from livekit.plugins import deepgram

    log = structlog.get_logger()
    api_key = _extract_key(org_keys, "deepgram")

    effective_model = model if model in _VALID_DEEPGRAM_MODELS else _DEEPGRAM_DEFAULT_MODEL
    if model and model != effective_model:
        log.warning(
            "deepgram_stt_invalid_model_fallback",
            requested=model,
            fallback=effective_model,
        )

    return deepgram.STT(
        api_key=api_key,
        language=language,
        model=effective_model,
        # Smart endpointing — uses Deepgram's finalization signal instead of
        # pure silence detection. Reduces cut-offs on natural mid-sentence pauses.
        endpointing_ms=200,
        interim_results=True,
    )


# ── Sarvam AI (Indian languages) ─────────────────────────────────────────────

def _build_sarvam(org_keys: dict, language: str):
    from vaaniq.voice.stt.sarvam import SarvamSTT

    api_key = _extract_key(org_keys, "sarvam")
    return SarvamSTT(api_key=api_key, language=language)


# ── AssemblyAI ────────────────────────────────────────────────────────────────

def _build_assemblyai(org_keys: dict, language: str):
    try:
        from livekit.plugins import assemblyai
    except ImportError as exc:
        raise ProviderNotFoundError("stt", "assemblyai") from exc

    api_key = _extract_key(org_keys, "assemblyai")
    return assemblyai.STT(api_key=api_key)


# ── OpenAI Whisper ────────────────────────────────────────────────────────────

def _build_openai(org_keys: dict, language: str, model: str | None):
    from livekit.plugins import openai as lk_openai

    api_key = _extract_key(org_keys, "openai")
    # BCP-47 codes like "en-US" → Whisper uses ISO 639-1 "en"
    whisper_lang = language.split("-")[0] if language else "en"
    return lk_openai.STT(
        api_key=api_key,
        language=whisper_lang,
        model=model or "gpt-4o-mini-transcribe",
    )


# ── Azure Speech (STT) ────────────────────────────────────────────────────────

def _build_azure_stt(org_keys: dict, language: str):
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

    return azure.STT(
        speech_key=speech_key,
        speech_region=region,
        language=language or "en-US",
    )


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
