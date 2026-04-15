"""OpenAI TTS provider — dynamic models via OpenAI API, static voices (no voices endpoint)."""

from __future__ import annotations

import structlog

from vaaniq.voice.providers._helpers import extract_key, resolve_model
from vaaniq.voice.providers.base import ModelInfo, TTSProviderBase, VoiceInfo
from vaaniq.voice.providers.registry import ProviderRegistry

log = structlog.get_logger()

_TTS_MODEL_PREFIXES = ("tts-1", "gpt-4o-mini-tts")


@ProviderRegistry.register_tts
class OpenAITTSProvider(TTSProviderBase):
    provider_id = "openai"
    display_name = "OpenAI TTS"

    _STATIC_MODELS = [
        ModelInfo("tts-1", "TTS-1", description="Standard quality. Optimised for real-time use.", languages=["*"], is_default=True),
        ModelInfo("tts-1-hd", "TTS-1 HD", description="Higher quality. Slightly higher latency.", languages=["*"]),
        ModelInfo("gpt-4o-mini-tts", "GPT-4o Mini TTS", description="Latest model. Most natural speech.", languages=["*"]),
    ]

    # OpenAI does NOT have a /voices endpoint — voices are fixed.
    # This list covers all voices for tts-1, tts-1-hd, and gpt-4o-mini-tts.
    _STATIC_VOICES = [
        VoiceInfo("alloy",   "Alloy",   gender="neutral", language="en", category="premade", description="Balanced, versatile"),
        VoiceInfo("ash",     "Ash",     gender="male",    language="en", category="premade", description="Warm and engaging"),
        VoiceInfo("ballad",  "Ballad",  gender="male",    language="en", category="premade", description="Expressive, emotional — gpt-4o-mini-tts only"),
        VoiceInfo("coral",   "Coral",   gender="female",  language="en", category="premade", description="Friendly and natural"),
        VoiceInfo("echo",    "Echo",    gender="male",    language="en", category="premade", description="Smooth and clear"),
        VoiceInfo("fable",   "Fable",   gender="neutral", language="en", category="premade", description="Warm British accent"),
        VoiceInfo("nova",    "Nova",    gender="female",  language="en", category="premade", description="Bright and optimistic"),
        VoiceInfo("onyx",    "Onyx",    gender="male",    language="en", category="premade", description="Deep and authoritative"),
        VoiceInfo("sage",    "Sage",    gender="female",  language="en", category="premade", description="Calm and thoughtful"),
        VoiceInfo("shimmer", "Shimmer", gender="female",  language="en", category="premade", description="Soft and gentle"),
    ]

    _VALID_VOICE_IDS = {v.id for v in _STATIC_VOICES}
    _DEFAULT_VOICE = "alloy"

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        return cls._STATIC_MODELS

    @classmethod
    async def fetch_models(cls, api_key: str) -> list[ModelInfo]:
        """
        Fetch TTS-capable models from the OpenAI Models API.

        GET https://api.openai.com/v1/models
        Authorization: Bearer <api_key>

        Filters to known TTS model prefixes. Falls back to static_models() on error.
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

            tts_models = [
                m for m in data.get("data", [])
                if any(m["id"].startswith(prefix) for prefix in _TTS_MODEL_PREFIXES)
            ]
            if not tts_models:
                return cls.static_models()

            order = {"tts-1": 0, "tts-1-hd": 1, "gpt-4o-mini-tts": 2}
            tts_models.sort(key=lambda m: order.get(m["id"], 99))

            return [
                ModelInfo(
                    id=m["id"],
                    display_name=_friendly_name(m["id"]),
                    languages=["*"],
                    is_default=(m["id"] == cls.default_model_id()),
                )
                for m in tts_models
            ]

        except Exception as exc:
            log.warning("openai_tts_models_fetch_failed", error=str(exc))
            return cls.static_models()

    @classmethod
    def supports_voices(cls) -> bool:
        return True

    @classmethod
    def static_voices(cls) -> list[VoiceInfo]:
        return cls._STATIC_VOICES

    # fetch_voices() intentionally not overridden — OpenAI has no voices endpoint.
    # static_voices() is always returned.

    @classmethod
    def default_model_id(cls) -> str:
        return "tts-1"

    @classmethod
    def create_plugin(cls, context):
        from livekit.plugins import openai as lk_openai

        api_key = extract_key(context.org_keys, "openai")
        model = resolve_model(context.tts_model, cls._STATIC_MODELS, cls.default_model_id(), "openai_tts")
        voice = context.agent_voice_id if context.agent_voice_id in cls._VALID_VOICE_IDS else cls._DEFAULT_VOICE
        kwargs: dict = {
            "api_key": api_key,
            "voice": voice,
            "model": model,
        }
        if context.tts_speed is not None:
            kwargs["speed"] = context.tts_speed
        return lk_openai.TTS(**kwargs)


def _friendly_name(model_id: str) -> str:
    names = {
        "tts-1": "TTS-1",
        "tts-1-hd": "TTS-1 HD",
        "gpt-4o-mini-tts": "GPT-4o Mini TTS",
    }
    return names.get(model_id, model_id)
