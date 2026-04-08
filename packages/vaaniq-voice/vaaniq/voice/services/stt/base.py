"""
STT provider factory.

Resolves the org's chosen provider (from BYOK integrations) to a configured
Pipecat STT service. All providers share the same factory interface so the
pipeline builder doesn't need to know which provider is in use.

Adding a new provider:
  1. Create vaaniq/voice/services/stt/<provider>.py with a create_<provider>_stt() function.
  2. Register it in STT_REGISTRY below.
  3. Add the provider name to vaaniq-server's context_builder._STT_PREFERENCE list.
"""

from typing import Any, Callable

from vaaniq.voice.constants import TWILIO_SAMPLE_RATE
from vaaniq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError


# Registry: provider name (as stored in integrations table) → factory function.
# Populated lazily to avoid importing heavy STT SDK dependencies at import time.
def _build_registry() -> dict[str, Callable]:
    from vaaniq.voice.services.stt.assemblyai import create_assemblyai_stt
    from vaaniq.voice.services.stt.deepgram import create_deepgram_stt

    return {
        "deepgram": create_deepgram_stt,
        "assemblyai": create_assemblyai_stt,
    }


def create_stt_service(
    provider: str,
    org_keys: dict,
    language: str = "en-US",
    model: str | None = None,
    sample_rate: int = TWILIO_SAMPLE_RATE,
) -> Any:  # Returns a Pipecat STTService subclass (lazily imported, varies by provider)
    """
    Resolve and instantiate an STT service from the registry.

    Args:
        provider:    Integration provider name, e.g. "deepgram" or "assemblyai".
        org_keys:    Decrypted BYOK keys for the org (provider → key value).
        language:    BCP-47 language tag, e.g. "en-US" or "hi-IN".
        sample_rate: Audio sample rate in Hz. Must match transport (8000 for Twilio).
    """
    registry = _build_registry()

    if provider not in registry:
        raise ProviderNotFoundError("STT", provider)

    # org_keys["deepgram"] may be a plain string key or a dict {"api_key": "..."}
    raw = org_keys.get(provider)
    if not raw:
        raise MissingAPIKeyError(provider)

    api_key = raw if isinstance(raw, str) else raw.get("api_key", "")
    if not api_key:
        raise MissingAPIKeyError(provider)

    kwargs = {"api_key": api_key, "language": language, "sample_rate": sample_rate}
    if model:
        kwargs["model"] = model
    return registry[provider](**kwargs)
