"""Cartesia TTS provider — static models (no models API), dynamic voices via Cartesia Voices API."""

from __future__ import annotations

import structlog

from naaviq.voice.providers._helpers import extract_key, resolve_model
from naaviq.voice.providers.base import ModelInfo, TTSProviderBase, VoiceInfo
from naaviq.voice.providers.registry import ProviderRegistry

log = structlog.get_logger()

_CARTESIA_API_VERSION = "2026-03-01"


@ProviderRegistry.register_tts
class CartesiaTTSProvider(TTSProviderBase):
    provider_id = "cartesia"
    display_name = "Cartesia"

    # Cartesia has no public models API — models are documented at docs.cartesia.ai
    _STATIC_MODELS = [
        ModelInfo("sonic-3", "Sonic 3", description="Latest model. Ultra-low latency (~40ms).", languages=["*"], is_default=True),
        ModelInfo("sonic-3-2026-01-12", "Sonic 3 (2026-01-12)", description="Latest stable snapshot.", languages=["*"]),
        ModelInfo("sonic-3-2025-10-27", "Sonic 3 (2025-10-27)", description="Previous stable snapshot.", languages=["*"]),
        ModelInfo("sonic-2", "Sonic 2 (legacy)", description="Previous generation.", languages=["*"]),
    ]

    # Cartesia has a small set of built-in public voices as a fallback.
    # The real list is fetched dynamically from the API.
    _STATIC_VOICES = [
        VoiceInfo("a0e99841-438c-4a64-b679-ae501e7d6091", "Default", category="premade", language="en"),
    ]

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        return cls._STATIC_MODELS

    # fetch_models() intentionally not overridden — Cartesia has no models API endpoint.
    # Model list is maintained statically from docs.cartesia.ai/build-with-cartesia/tts-models

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
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.cartesia.ai/voices",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Cartesia-Version": _CARTESIA_API_VERSION,
                    },
                )
                resp.raise_for_status()
                raw = resp.json()

            # Cartesia returns a plain JSON array (not a paginated wrapper)
            items: list = raw if isinstance(raw, list) else raw.get("data", raw.get("voices", []))

            voices = [
                VoiceInfo(
                    id=v["id"],
                    name=v.get("name", v["id"]),
                    preview_url=v.get("preview_file_url") or v.get("preview_url"),
                    gender=_normalise_gender(v.get("gender")),
                    language=v.get("language"),
                    description=v.get("description"),
                    category="premade" if v.get("is_public") else "custom",
                )
                for v in items
                if v.get("id")
            ]

            return voices if voices else cls.static_voices()

        except Exception as exc:
            log.warning("cartesia_voices_fetch_failed", error=str(exc))
            return cls.static_voices()

    @classmethod
    async def synthesize_preview(cls, text: str, config: dict, api_key: str) -> tuple[bytes, str] | None:
        import httpx

        voice_id = config.get("tts_voice_id") or "a0e99841-438c-4a64-b679-ae501e7d6091"
        model_id = config.get("tts_model") or cls.default_model_id()
        speed = config.get("tts_speed") or 1.0
        emotion = config.get("tts_emotion")

        payload: dict = {
            "model_id": model_id,
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "output_format": {
                "container": "mp3",
                "bit_rate": 128000,
                "sample_rate": 44100,
            },
            "language": "en",
        }
        if speed != 1.0:
            payload["speed"] = speed
        if emotion:
            payload["emotion"] = [emotion]

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.cartesia.ai/tts/bytes",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Cartesia-Version": _CARTESIA_API_VERSION,
                    },
                    json=payload,
                )
                if resp.status_code == 200:
                    return resp.content, "audio/mpeg"
        except Exception as exc:
            log.warning("cartesia_tts_preview_failed", error=str(exc))
        return None

    @classmethod
    def default_model_id(cls) -> str:
        return "sonic-3"

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
        if context.tts_emotion:
            kwargs["emotion"] = [context.tts_emotion]
        return cartesia.TTS(**kwargs)


def _normalise_gender(raw: str | None) -> str | None:
    if not raw:
        return None
    mapping = {"masculine": "male", "feminine": "female", "gender_neutral": "neutral"}
    return mapping.get(raw.lower(), raw.lower())
