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

    raise ProviderNotFoundError("stt", provider)


# ── Deepgram ──────────────────────────────────────────────────────────────────

def _build_deepgram(org_keys: dict, language: str, model: str | None):
    from livekit.plugins import deepgram

    api_key = _extract_key(org_keys, "deepgram")
    return deepgram.STT(
        api_key=api_key,
        language=language,
        model=model or "nova-3",
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
