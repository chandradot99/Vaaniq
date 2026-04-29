"""Deepgram STT provider — dynamic model listing via Deepgram Models API."""

from __future__ import annotations

import structlog

from naaviq.voice.providers._helpers import extract_key, resolve_model
from naaviq.voice.providers.base import ModelInfo, STTProviderBase
from naaviq.voice.providers.registry import ProviderRegistry

log = structlog.get_logger()

# Languages supported by Nova-3 (50+) — ISO 639-1 or BCP-47
_NOVA3_LANGS = [
    "en", "en-US", "en-GB", "en-AU", "en-IN", "en-NZ",
    "hi", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "ur",
    "ar", "zh", "zh-CN", "zh-TW", "fr", "fr-CA", "de", "es", "es-419",
    "pt", "pt-BR", "pt-PT", "ja", "ko", "it", "nl", "pl", "ru", "sv",
    "tr", "id", "th", "vi", "uk", "cs", "el", "fi", "da", "hu", "no",
    "ro", "bg", "sk", "hr", "ms", "he", "fa",
]

# Languages supported by Nova-2 (40+)
_NOVA2_LANGS = [
    "en", "en-US", "en-GB", "en-AU", "en-IN",
    "hi", "ta", "te", "fr", "de", "es", "pt", "pt-BR",
    "ja", "ko", "it", "nl", "ru", "tr", "id", "sv", "da", "zh",
    "fi", "el", "bg", "ro", "uk", "cs", "hr", "sk", "ms",
]


@ProviderRegistry.register_stt
class DeepgramSTTProvider(STTProviderBase):
    provider_id = "deepgram"
    display_name = "Deepgram"

    _STATIC_MODELS = [
        # ── Current generation ────────────────────────────────────────────────
        ModelInfo(
            "nova-3",
            "Nova 3",
            description="Best accuracy. 50+ languages including Indian languages. Recommended for most voice agents.",
            languages=_NOVA3_LANGS,
            is_default=True,
            streaming=True,
            category="Current Generation",
        ),
        ModelInfo(
            "nova-3-medical",
            "Nova 3 Medical",
            description="Nova 3 fine-tuned for medical and clinical terminology.",
            languages=["en"],
            is_default=False,
            streaming=True,
            category="Current Generation",
        ),
        ModelInfo(
            "flux-general-en",
            "Flux",
            description="Voice-agent optimised. Built-in end-of-turn detection. Ultra-low latency. English only.",
            languages=["en"],
            is_default=False,
            streaming=True,
            category="Current Generation",
        ),
        # ── Previous generation — use when language not yet in Nova 3 ─────────
        ModelInfo(
            "nova-2",
            "Nova 2",
            description="General purpose. Use for languages not yet supported by Nova 3.",
            languages=_NOVA2_LANGS,
            is_default=False,
            streaming=True,
            category="Previous Generation",
        ),
        ModelInfo(
            "nova-2-phonecall",
            "Nova 2 Phone Call",
            description="Optimised for phone audio (8 kHz PSTN calls). English only.",
            languages=["en"],
            is_default=False,
            streaming=True,
            category="Previous Generation",
        ),
        ModelInfo(
            "nova-2-conversationalai",
            "Nova 2 Conversational AI",
            description="Fine-tuned for voice agent conversations. English only.",
            languages=["en"],
            is_default=False,
            streaming=True,
            category="Previous Generation",
        ),
        ModelInfo(
            "nova-2-meeting",
            "Nova 2 Meeting",
            description="Multi-speaker meeting transcription. English only.",
            languages=["en"],
            is_default=False,
            streaming=True,
            category="Previous Generation",
        ),
        ModelInfo(
            "nova-2-finance",
            "Nova 2 Finance",
            description="Financial and banking terminology. English only.",
            languages=["en"],
            is_default=False,
            streaming=True,
            category="Previous Generation",
        ),
        ModelInfo(
            "nova-2-medical",
            "Nova 2 Medical",
            description="Medical and clinical terminology. English only.",
            languages=["en"],
            is_default=False,
            streaming=True,
            category="Previous Generation",
        ),
    ]

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        return cls._STATIC_MODELS

    @classmethod
    async def fetch_models(cls, api_key: str) -> list[ModelInfo]:
        """
        Deepgram's /v1/models API returns hundreds of entries including legacy,
        deprecated, and custom models. We use the curated static list instead
        so the UI stays clean and informative.
        """
        return cls.static_models()

    @classmethod
    def default_model_id(cls) -> str:
        return "nova-3"

    @classmethod
    def create_plugin(cls, context):
        from livekit.plugins import deepgram

        api_key = extract_key(context.org_keys, cls.provider_id)
        model = resolve_model(context.stt_model, cls._STATIC_MODELS, cls.default_model_id(), "deepgram_stt")
        return deepgram.STT(
            api_key=api_key,
            language=context.agent_language,
            model=model,
            endpointing_ms=200,
            interim_results=True,
        )
