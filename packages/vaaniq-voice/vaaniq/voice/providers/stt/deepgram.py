"""Deepgram STT provider — dynamic model listing via Deepgram Models API."""

from __future__ import annotations

import structlog

from vaaniq.voice.providers._helpers import extract_key, resolve_model
from vaaniq.voice.providers.base import ModelInfo, STTProviderBase
from vaaniq.voice.providers.registry import ProviderRegistry

log = structlog.get_logger()


@ProviderRegistry.register_stt
class DeepgramSTTProvider(STTProviderBase):
    provider_id = "deepgram"
    display_name = "Deepgram"

    _STATIC_MODELS = [
        ModelInfo("nova-3", "Nova 3", description="Latest model. Best accuracy and speed.", languages=["*"], is_default=True),
        ModelInfo("nova-2", "Nova 2", description="Previous generation. Widely deployed.", languages=["*"]),
        ModelInfo("nova-2-phonecall", "Nova 2 Phone Call", description="Optimised for phone audio (8kHz).", languages=["en"]),
        ModelInfo("nova-2-finance", "Nova 2 Finance", description="Financial and banking terminology.", languages=["en"]),
        ModelInfo("nova-2-meeting", "Nova 2 Meeting", description="Multi-speaker meeting transcription.", languages=["en"]),
        ModelInfo("nova-2-medical", "Nova 2 Medical", description="Medical and clinical terminology.", languages=["en"]),
        ModelInfo("nova-2-conversationalai", "Nova 2 Conversational AI", description="Tuned for conversational agent use cases.", languages=["en"]),
        ModelInfo("enhanced", "Enhanced", languages=["*"]),
        ModelInfo("base", "Base", languages=["*"]),
    ]

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        return cls._STATIC_MODELS

    @classmethod
    async def fetch_models(cls, api_key: str) -> list[ModelInfo]:
        """
        Fetch available STT models from the Deepgram Models API.

        GET https://api.deepgram.com/v1/models
        Authorization: Token <api_key>

        Falls back to static_models() on any error.
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.deepgram.com/v1/models",
                    headers={"Authorization": f"Token {api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()

            models = []
            for m in data.get("stt", []):
                # Only include streaming-capable models
                if not m.get("streaming", True):
                    continue
                models.append(ModelInfo(
                    id=m["name"],
                    display_name=m.get("canonical_name") or m["name"],
                    languages=m.get("languages", []),
                    is_default=(m["name"] == cls.default_model_id()),
                ))
            return models if models else cls.static_models()

        except Exception as exc:
            log.warning("deepgram_models_fetch_failed", error=str(exc))
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
