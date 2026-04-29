"""
STT provider factory for naaviq-voice.

Thin wrapper around the provider registry. All STT logic lives in
naaviq.voice.providers.stt.*  — add new providers there.
"""

# Ensure all providers are registered before any lookup
import naaviq.voice.providers  # noqa: F401

from naaviq.voice.pipeline.context import VoiceCallContext
from naaviq.voice.providers.registry import ProviderRegistry


def create_stt_plugin(context: VoiceCallContext):
    """
    Return a LiveKit STT plugin for the provider specified in the call context.

    Raises:
        ProviderNotFoundError: provider is not registered.
        MissingAPIKeyError: org has no API key for the provider.
    """
    provider = ProviderRegistry.get_stt(context.stt_provider)
    return provider.create_plugin(context)
