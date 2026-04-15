"""Cartesia TTS provider — static models, dynamic voices via Cartesia Voices API."""

from __future__ import annotations

import structlog

from vaaniq.voice.providers._helpers import extract_key, resolve_model
from vaaniq.voice.providers.base import ModelInfo, TTSProviderBase, VoiceInfo
from vaaniq.voice.providers.registry import ProviderRegistry

log = structlog.get_logger()

_CARTESIA_API_VERSION = "2025-04-16"


@ProviderRegistry.register_tts
class CartesiaTTSProvider(TTSProviderBase):
    provider_id = "cartesia"
    display_name = "Cartesia"

    _STATIC_MODELS = [
        ModelInfo("sonic-2", "Sonic 2", description="Default model. Ultra-low latency (~90ms).", languages=["*"], is_default=True),
        ModelInfo("sonic-english", "Sonic English", description="English-only variant.", languages=["en"]),
        ModelInfo("sonic-multilingual", "Sonic Multilingual", description="Multilingual support.", languages=["*"]),
    ]

    # Cartesia has a small set of built-in public voices as a fallback.
    # The real list is fetched dynamically from the API.
    _STATIC_VOICES = [
        VoiceInfo("a0e99841-438c-4a64-b679-ae501e7d6091", "Default", category="premade", language="en"),
    ]

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        return cls._STATIC_MODELS

    @classmethod
    def supports_voices(cls) -> bool:
        return True

    @classmethod
    def static_voices(cls) -> list[VoiceInfo]:
        return cls._STATIC_VOICES

    @classmethod
    async def fetch_voices(cls, api_key: str) -> list[VoiceInfo]:
        """
        Fetch available voices from the Cartesia Voices API.

        GET https://api.cartesia.ai/voices
        Authorization: Bearer <api_key>
        Cartesia-Version: <version>

        Falls back to static_voices() on any error.
        """
        import httpx

        try:
            voices: list[VoiceInfo] = []
            url: str | None = "https://api.cartesia.ai/voices"

            async with httpx.AsyncClient(timeout=10.0) as client:
                while url:
                    resp = await client.get(
                        url,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Cartesia-Version": _CARTESIA_API_VERSION,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for v in data.get("data", []):
                        voices.append(VoiceInfo(
                            id=v["id"],
                            name=v.get("name", v["id"]),
                            preview_url=v.get("preview_file_url"),
                            gender=_normalise_gender(v.get("gender")),
                            language=v.get("language"),
                            description=v.get("description"),
                            category="premade" if v.get("is_public") else "custom",
                        ))

                    # Pagination
                    url = data.get("next_page") if data.get("has_more") else None

            return voices if voices else cls.static_voices()

        except Exception as exc:
            log.warning("cartesia_voices_fetch_failed", error=str(exc))
            return cls.static_voices()

    @classmethod
    def default_model_id(cls) -> str:
        return "sonic-2"

    @classmethod
    def create_plugin(cls, context):
        from livekit.plugins import cartesia

        api_key = extract_key(context.org_keys, cls.provider_id)
        model = resolve_model(context.tts_model, cls._STATIC_MODELS, cls.default_model_id(), "cartesia_tts")
        kwargs: dict = {
            "api_key": api_key,
            "voice": context.agent_voice_id or "a0e99841-438c-4a64-b679-ae501e7d6091",
            "model": model,
            "language": context.agent_language[:2].lower() if context.agent_language else "en",
            "encoding": "pcm_s16le",
            "sample_rate": 24000,
        }
        if context.tts_speed is not None:
            kwargs["speed"] = context.tts_speed
        return cartesia.TTS(**kwargs)


def _normalise_gender(raw: str | None) -> str | None:
    if not raw:
        return None
    mapping = {"masculine": "male", "feminine": "female", "gender_neutral": "neutral"}
    return mapping.get(raw.lower(), raw.lower())
