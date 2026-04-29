"""OpenAI TTS provider — dynamic models via OpenAI API, static voices (no voices endpoint)."""

from __future__ import annotations

import structlog

from naaviq.voice.providers._helpers import extract_key, resolve_model
from naaviq.voice.providers.base import ModelInfo, TTSProviderBase, VoiceInfo
from naaviq.voice.providers.registry import ProviderRegistry

log = structlog.get_logger()

_TTS_MODEL_PREFIXES = ("tts-1", "gpt-4o-mini-tts")

# Voices exclusive to gpt-4o-mini-tts
_MINI_TTS_ONLY_VOICES = {"verse", "marin", "cedar"}


@ProviderRegistry.register_tts
class OpenAITTSProvider(TTSProviderBase):
    provider_id = "openai"
    display_name = "OpenAI TTS"

    _STATIC_MODELS = [
        ModelInfo(
            "gpt-4o-mini-tts",
            "GPT-4o Mini TTS",
            description="Latest model. Most natural speech. Instruction-following.",
            languages=["*"],
            is_default=True,
            streaming=True,
        ),
        ModelInfo(
            "tts-1",
            "TTS-1",
            description="Standard quality. Optimised for real-time use.",
            languages=["*"],
            is_default=False,
            streaming=True,
        ),
        ModelInfo(
            "tts-1-hd",
            "TTS-1 HD",
            description="Higher quality. Slightly higher latency.",
            languages=["*"],
            is_default=False,
            streaming=True,
        ),
    ]

    # OpenAI does NOT have a /voices endpoint — voices are fixed.
    # verse, marin, cedar are only available on gpt-4o-mini-tts.
    # language is intentionally omitted — OpenAI voices are multilingual; the voice
    # character does not restrict the language, the input text determines it.
    _STATIC_VOICES = [
        VoiceInfo("alloy",   "Alloy",   gender="neutral", category="premade", description="Balanced, versatile"),
        VoiceInfo("ash",     "Ash",     gender="male",    category="premade", description="Warm and engaging"),
        VoiceInfo("ballad",  "Ballad",  gender="male",    category="premade", description="Expressive, emotional — gpt-4o-mini-tts only"),
        VoiceInfo("cedar",   "Cedar",   gender="male",    category="premade", description="Clear and professional — gpt-4o-mini-tts only"),
        VoiceInfo("coral",   "Coral",   gender="female",  category="premade", description="Friendly and natural"),
        VoiceInfo("echo",    "Echo",    gender="male",    category="premade", description="Smooth and clear"),
        VoiceInfo("fable",   "Fable",   gender="neutral", category="premade", description="Warm British accent"),
        VoiceInfo("marin",   "Marin",   gender="female",  category="premade", description="Energetic and expressive — gpt-4o-mini-tts only"),
        VoiceInfo("nova",    "Nova",    gender="female",  category="premade", description="Bright and optimistic"),
        VoiceInfo("onyx",    "Onyx",    gender="male",    category="premade", description="Deep and authoritative"),
        VoiceInfo("sage",    "Sage",    gender="female",  category="premade", description="Calm and thoughtful"),
        VoiceInfo("shimmer", "Shimmer", gender="female",  category="premade", description="Soft and gentle"),
        VoiceInfo("verse",   "Verse",   gender="male",    category="premade", description="Conversational and natural — gpt-4o-mini-tts only"),
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

            order = {"gpt-4o-mini-tts": 0, "tts-1": 1, "tts-1-hd": 2}
            tts_models.sort(key=lambda m: order.get(m["id"], 99))

            return [
                ModelInfo(
                    id=m["id"],
                    display_name=_friendly_name(m["id"]),
                    languages=["*"],
                    is_default=(m["id"] == cls.default_model_id()),
                    streaming=True,
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
    async def synthesize_preview(cls, text: str, config: dict, api_key: str) -> tuple[bytes, str] | None:
        import httpx

        voice = config.get("tts_voice_id") or cls._DEFAULT_VOICE
        if voice not in cls._VALID_VOICE_IDS:
            voice = cls._DEFAULT_VOICE
        model = config.get("tts_model") or cls.default_model_id()
        speed = config.get("tts_speed") or 1.0
        instructions = config.get("tts_instructions")

        payload: dict = {
            "model": model,
            "input": text,
            "voice": voice,
            "speed": speed,
            "response_format": "mp3",
        }
        if instructions:
            payload["instructions"] = instructions

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
                if resp.status_code == 200:
                    return resp.content, "audio/mpeg"
        except Exception as exc:
            log.warning("openai_tts_preview_failed", error=str(exc))
        return None

    @classmethod
    def default_model_id(cls) -> str:
        return "gpt-4o-mini-tts"

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
        if context.tts_instructions:
            kwargs["instructions"] = context.tts_instructions
        return lk_openai.TTS(**kwargs)


def _friendly_name(model_id: str) -> str:
    names = {
        "gpt-4o-mini-tts": "GPT-4o Mini TTS",
        "tts-1": "TTS-1",
        "tts-1-hd": "TTS-1 HD",
    }
    return names.get(model_id, model_id)
