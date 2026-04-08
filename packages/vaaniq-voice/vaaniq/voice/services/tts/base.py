"""
TTS provider factory.

Resolves the org's chosen provider (from BYOK integrations) to a configured
Pipecat TTS service. All providers share the same factory interface so the
pipeline builder doesn't need to know which provider is in use.

Adding a new provider:
  1. Create vaaniq/voice/services/tts/<provider>.py with a create_<provider>_tts() function.
  2. Register it in TTS_REGISTRY below.
  3. Add the provider name to vaaniq-server's context_builder._TTS_PREFERENCE list.
"""

from typing import Any, Callable, Optional

from vaaniq.voice.constants import TWILIO_SAMPLE_RATE
from vaaniq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError


def _build_registry() -> dict[str, Callable]:
    from vaaniq.voice.services.tts.cartesia import create_cartesia_tts
    from vaaniq.voice.services.tts.deepgram import create_deepgram_tts
    from vaaniq.voice.services.tts.elevenlabs import create_elevenlabs_tts
    from vaaniq.voice.services.tts.azure import create_azure_tts

    return {
        "cartesia": create_cartesia_tts,
        "deepgram": create_deepgram_tts,
        "elevenlabs": create_elevenlabs_tts,
        "azure": create_azure_tts,
    }


def create_tts_service(
    provider: str,
    org_keys: dict,
    voice_id: Optional[str] = None,
    model: Optional[str] = None,
    speed: Optional[float] = None,
    language: str = "en-US",
    sample_rate: int = TWILIO_SAMPLE_RATE,
) -> Any:  # Returns a Pipecat TTSService subclass (lazily imported, varies by provider)
    """
    Resolve and instantiate a TTS service from the registry.

    Args:
        provider:    Integration provider name, e.g. "cartesia" or "elevenlabs".
        org_keys:    Decrypted BYOK keys for the org (provider → key value).
        voice_id:    Optional voice ID / name. Provider default used if not set.
        language:    BCP-47 language tag — used by Azure to auto-select voice.
        sample_rate: Audio sample rate in Hz. Must match transport (8000 for Twilio).
    """
    registry = _build_registry()

    if provider not in registry:
        raise ProviderNotFoundError("TTS", provider)

    raw = org_keys.get(provider)
    if not raw:
        raise MissingAPIKeyError(provider)

    api_key = raw if isinstance(raw, str) else raw.get("api_key", "")
    if not api_key:
        raise MissingAPIKeyError(provider)

    # Azure also needs a region — stored in org_keys["azure"] as {"api_key": "...", "region": "..."}
    if provider == "azure":
        region = None if isinstance(raw, str) else raw.get("region")
        return registry[provider](
            api_key=api_key,
            voice_id=voice_id,
            language=language,
            region=region,
            sample_rate=sample_rate,
        )

    kwargs: dict = {"api_key": api_key, "voice_id": voice_id, "sample_rate": sample_rate}
    if model:
        kwargs["model"] = model
    if speed is not None:
        kwargs["speed"] = speed
    return registry[provider](**kwargs)
