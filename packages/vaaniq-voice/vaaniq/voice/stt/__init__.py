"""
STT provider factory for vaaniq-voice (LiveKit Agents).

Returns a LiveKit STT plugin instance for the requested provider.
Providers are loaded lazily to avoid importing SDKs that aren't installed.

All builder functions validate the requested model against a known-good set and
fall back to the provider default with a warning log rather than crashing the
AgentSession with a remote 400/authentication error.
"""

import structlog
from vaaniq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError
from vaaniq.voice.pipeline.context import VoiceCallContext

log = structlog.get_logger()


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

_VALID_DEEPGRAM_STT_MODELS = {
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
_DEEPGRAM_STT_DEFAULT = "nova-3"


def _build_deepgram(org_keys: dict, language: str, model: str | None):
    from livekit.plugins import deepgram

    api_key = _extract_key(org_keys, "deepgram")
    effective_model = _sanitize_model(
        model, _VALID_DEEPGRAM_STT_MODELS, _DEEPGRAM_STT_DEFAULT, "deepgram_stt"
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


# ── OpenAI Whisper ────────────────────────────────────────────────────────────

_VALID_OPENAI_STT_MODELS = {
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe",
    "whisper-1",
}
_OPENAI_STT_DEFAULT = "gpt-4o-mini-transcribe"


def _build_openai(org_keys: dict, language: str, model: str | None):
    from livekit.plugins import openai as lk_openai

    api_key = _extract_key(org_keys, "openai")
    # BCP-47 codes like "en-US" → Whisper uses ISO 639-1 "en"
    whisper_lang = language.split("-")[0] if language else "en"
    effective_model = _sanitize_model(
        model, _VALID_OPENAI_STT_MODELS, _OPENAI_STT_DEFAULT, "openai_stt"
    )
    return lk_openai.STT(
        api_key=api_key,
        language=whisper_lang,
        model=effective_model,
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

def _sanitize_model(
    model: str | None,
    valid: set[str],
    default: str,
    provider_label: str,
) -> str:
    """
    Return `model` if it is in the valid set, otherwise return `default`.

    Logs a warning when an unrecognised model is replaced so operators can
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
