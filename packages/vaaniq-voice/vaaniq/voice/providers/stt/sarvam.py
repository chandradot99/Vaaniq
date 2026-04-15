"""Sarvam AI STT provider — static models (no public models API)."""

from __future__ import annotations

from vaaniq.voice.providers._helpers import extract_key
from vaaniq.voice.providers.base import ModelInfo, STTProviderBase
from vaaniq.voice.providers.registry import ProviderRegistry


@ProviderRegistry.register_stt
class SarvamSTTProvider(STTProviderBase):
    provider_id = "sarvam"
    display_name = "Sarvam AI"

    _STATIC_MODELS = [
        ModelInfo("saarika:v2", "Saarika v2", description="Latest model. Best accuracy for Indian languages.", languages=["hi-IN", "ta-IN", "te-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "or-IN", "en-IN"], is_default=True),
        ModelInfo("saarika:flash", "Saarika Flash", description="Low-latency variant. Slightly lower accuracy.", languages=["hi-IN", "ta-IN", "te-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "or-IN", "en-IN"]),
        ModelInfo("saarika:v1", "Saarika v1", description="Legacy model.", languages=["hi-IN", "ta-IN", "te-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "or-IN", "en-IN"]),
    ]

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        return cls._STATIC_MODELS

    # fetch_models() intentionally not overridden — Sarvam has no models endpoint.

    @classmethod
    def default_model_id(cls) -> str:
        return "saarika:v2"

    @classmethod
    def create_plugin(cls, context):
        from vaaniq.voice.stt.sarvam import SarvamSTT

        api_key = extract_key(context.org_keys, cls.provider_id)
        return SarvamSTT(api_key=api_key, language=context.agent_language)
