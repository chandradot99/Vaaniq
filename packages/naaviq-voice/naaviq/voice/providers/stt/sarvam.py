"""Sarvam AI STT provider — static models (no public models API)."""

from __future__ import annotations

from naaviq.voice.providers._helpers import extract_key
from naaviq.voice.providers.base import ModelInfo, STTProviderBase
from naaviq.voice.providers.registry import ProviderRegistry

_SARVAM_LANGS = [
    "hi-IN", "ta-IN", "te-IN", "bn-IN", "gu-IN",
    "kn-IN", "ml-IN", "mr-IN", "pa-IN", "or-IN", "en-IN",
]


@ProviderRegistry.register_stt
class SarvamSTTProvider(STTProviderBase):
    provider_id = "sarvam"
    display_name = "Sarvam AI"
    languages = _SARVAM_LANGS

    _STATIC_MODELS = [
        ModelInfo(
            "saaras:v3",
            "Saaras v3",
            description="Best accuracy for Indian languages. Real-time streaming. Recommended.",
            languages=_SARVAM_LANGS,
            is_default=True,
            streaming=True,
        ),
        ModelInfo(
            "saarika:v2.5",
            "Saarika v2.5",
            description="Batch transcription only. Not for real-time voice calls.",
            languages=_SARVAM_LANGS,
            is_default=False,
            streaming=False,
        ),
    ]

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        return cls._STATIC_MODELS

    # fetch_models() intentionally not overridden — Sarvam has no models endpoint.

    @classmethod
    def default_model_id(cls) -> str:
        return "saaras:v3"

    @classmethod
    def create_plugin(cls, context):
        from naaviq.voice.stt.sarvam import SarvamSTT

        api_key = extract_key(context.org_keys, cls.provider_id)
        return SarvamSTT(api_key=api_key, language=context.agent_language)
