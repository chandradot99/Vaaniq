"""OpenAI Whisper STT provider — dynamic model listing via OpenAI Models API."""

from __future__ import annotations

import structlog

from vaaniq.voice.providers._helpers import extract_key, resolve_model
from vaaniq.voice.providers.base import ModelInfo, STTProviderBase
from vaaniq.voice.providers.registry import ProviderRegistry

log = structlog.get_logger()

# Model ID prefixes that identify OpenAI STT models in the /v1/models listing
_STT_MODEL_PREFIXES = ("whisper", "gpt-4o-transcribe", "gpt-4o-mini-transcribe")


@ProviderRegistry.register_stt
class OpenAISTTProvider(STTProviderBase):
    provider_id = "openai"
    display_name = "OpenAI Whisper"

    _STATIC_MODELS = [
        ModelInfo("gpt-4o-mini-transcribe", "GPT-4o Mini Transcribe", description="Fast, cost-effective transcription.", languages=["*"], is_default=True),
        ModelInfo("gpt-4o-transcribe", "GPT-4o Transcribe", description="Highest accuracy. Slower and more expensive.", languages=["*"]),
        ModelInfo("whisper-1", "Whisper 1", description="Classic Whisper model. Broad language support.", languages=["*"]),
    ]

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        return cls._STATIC_MODELS

    @classmethod
    async def fetch_models(cls, api_key: str) -> list[ModelInfo]:
        """
        Fetch STT-capable models from the OpenAI Models API.

        GET https://api.openai.com/v1/models
        Authorization: Bearer <api_key>

        Filters the response to known STT model prefixes. Falls back to
        static_models() on any error.
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()

            stt_models = [
                m for m in data.get("data", [])
                if any(m["id"].startswith(prefix) for prefix in _STT_MODEL_PREFIXES)
            ]
            if not stt_models:
                return cls.static_models()

            # Sort: gpt-4o-mini-transcribe first, then gpt-4o-transcribe, then whisper
            order = {"gpt-4o-mini-transcribe": 0, "gpt-4o-transcribe": 1, "whisper-1": 2}
            stt_models.sort(key=lambda m: order.get(m["id"], 99))

            return [
                ModelInfo(
                    id=m["id"],
                    display_name=_friendly_name(m["id"]),
                    languages=["*"],
                    is_default=(m["id"] == cls.default_model_id()),
                )
                for m in stt_models
            ]

        except Exception as exc:
            log.warning("openai_stt_models_fetch_failed", error=str(exc))
            return cls.static_models()

    @classmethod
    def default_model_id(cls) -> str:
        return "gpt-4o-mini-transcribe"

    @classmethod
    def create_plugin(cls, context):
        from livekit.plugins import openai as lk_openai

        api_key = extract_key(context.org_keys, "openai")
        model = resolve_model(context.stt_model, cls._STATIC_MODELS, cls.default_model_id(), "openai_stt")
        # OpenAI STT uses ISO 639-1 codes ("en"), not BCP-47 ("en-US")
        language = context.agent_language.split("-")[0] if context.agent_language else "en"
        return lk_openai.STT(
            api_key=api_key,
            language=language,
            model=model,
        )


def _friendly_name(model_id: str) -> str:
    names = {
        "gpt-4o-mini-transcribe": "GPT-4o Mini Transcribe",
        "gpt-4o-transcribe": "GPT-4o Transcribe",
        "whisper-1": "Whisper 1",
    }
    return names.get(model_id, model_id)
