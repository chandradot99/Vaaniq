"""ElevenLabs TTS provider — dynamic models AND voices via ElevenLabs API."""

from __future__ import annotations

import structlog

from vaaniq.voice.providers._helpers import extract_key, resolve_model
from vaaniq.voice.providers.base import ModelInfo, TTSProviderBase, VoiceInfo
from vaaniq.voice.providers.registry import ProviderRegistry

log = structlog.get_logger()


@ProviderRegistry.register_tts
class ElevenLabsTTSProvider(TTSProviderBase):
    provider_id = "elevenlabs"
    display_name = "ElevenLabs"

    _STATIC_MODELS = [
        ModelInfo("eleven_flash_v2_5", "Flash v2.5", description="Lowest latency. Best for real-time voice.", languages=["*"], is_default=True),
        ModelInfo("eleven_turbo_v2_5", "Turbo v2.5", description="Balanced latency and quality.", languages=["*"]),
        ModelInfo("eleven_turbo_v2", "Turbo v2", description="Previous turbo generation.", languages=["en"]),
        ModelInfo("eleven_multilingual_v2", "Multilingual v2", description="Highest quality. 29 languages.", languages=["*"]),
        ModelInfo("eleven_multilingual_v1", "Multilingual v1", description="Legacy multilingual.", languages=["*"]),
        ModelInfo("eleven_monolingual_v1", "Monolingual v1", description="Legacy English-only.", languages=["en"]),
    ]

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        return cls._STATIC_MODELS

    @classmethod
    async def fetch_models(cls, api_key: str) -> list[ModelInfo]:
        """
        Fetch available models from the ElevenLabs Models API.

        GET https://api.elevenlabs.io/v1/models
        xi-api-key: <api_key>

        Falls back to static_models() on any error.
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.elevenlabs.io/v1/models",
                    headers={"xi-api-key": api_key},
                )
                resp.raise_for_status()
                data = resp.json()

            models = []
            for m in data:
                if not m.get("can_do_text_to_speech"):
                    continue
                model_id = m["model_id"]
                languages = [lang["language_id"] for lang in m.get("languages", [])]
                models.append(ModelInfo(
                    id=model_id,
                    display_name=m.get("name", model_id),
                    description=m.get("description"),
                    languages=languages or ["*"],
                    is_default=(model_id == cls.default_model_id()),
                ))
            return models if models else cls.static_models()

        except Exception as exc:
            log.warning("elevenlabs_models_fetch_failed", error=str(exc))
            return cls.static_models()

    @classmethod
    def supports_voices(cls) -> bool:
        return True

    @classmethod
    def static_voices(cls) -> list[VoiceInfo]:
        # A handful of ElevenLabs pre-made voices as fallback
        return [
            VoiceInfo("21m00Tcm4TlvDq8ikWAM", "Rachel", gender="female", language="en", category="premade", description="Calm, young American female"),
            VoiceInfo("AZnzlk1XvdvUeBnXmlld", "Domi", gender="female", language="en", category="premade", description="Strong, confident American female"),
            VoiceInfo("EXAVITQu4vr4xnSDxMaL", "Bella", gender="female", language="en", category="premade", description="Soft, expressive American female"),
            VoiceInfo("ErXwobaYiN019PkySvjV", "Antoni", gender="male", language="en", category="premade", description="Warm, professional American male"),
            VoiceInfo("MF3mGyEYCl7XYWbV9V6O", "Elli", gender="female", language="en", category="premade", description="Emotional, young American female"),
            VoiceInfo("TxGEqnHWrfWFTfGW9XjX", "Josh", gender="male", language="en", category="premade", description="Deep, young American male"),
            VoiceInfo("VR6AewLTigWG4xSOukaG", "Arnold", gender="male", language="en", category="premade", description="Crisp, middle-aged American male"),
            VoiceInfo("pNInz6obpgDQGcFmaJgB", "Adam", gender="male", language="en", category="premade", description="Deep, mature American male"),
            VoiceInfo("yoZ06aMxZJJ28mfd3POQ", "Sam", gender="male", language="en", category="premade", description="Raspy, young American male"),
        ]

    @classmethod
    async def fetch_voices(cls, api_key: str) -> list[VoiceInfo]:
        """
        Fetch available voices from the ElevenLabs Voices API.

        GET https://api.elevenlabs.io/v2/voices
        xi-api-key: <api_key>

        Returns both the org's own voices and public pre-made voices.
        Falls back to static_voices() on any error.
        """
        import httpx

        try:
            voices: list[VoiceInfo] = []
            url: str | None = "https://api.elevenlabs.io/v2/voices"
            next_page_token: str | None = None

            async with httpx.AsyncClient(timeout=10.0) as client:
                while url:
                    params = {}
                    if next_page_token:
                        params["next_page_token"] = next_page_token

                    resp = await client.get(
                        url,
                        headers={"xi-api-key": api_key},
                        params=params,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for v in data.get("voices", []):
                        voices.append(VoiceInfo(
                            id=v["voice_id"],
                            name=v.get("name", v["voice_id"]),
                            preview_url=v.get("preview_url"),
                            category=v.get("category"),
                            description=v.get("description"),
                            # ElevenLabs labels are freeform; pull gender if present
                            gender=v.get("labels", {}).get("gender"),
                            language=v.get("labels", {}).get("language"),
                        ))

                    if data.get("has_more"):
                        next_page_token = data.get("next_page_token")
                        if not next_page_token:
                            break
                    else:
                        break

            return voices if voices else cls.static_voices()

        except Exception as exc:
            log.warning("elevenlabs_voices_fetch_failed", error=str(exc))
            return cls.static_voices()

    @classmethod
    def default_model_id(cls) -> str:
        return "eleven_flash_v2_5"

    @classmethod
    def create_plugin(cls, context):
        from livekit.plugins import elevenlabs

        api_key = extract_key(context.org_keys, cls.provider_id)
        model = resolve_model(context.tts_model, cls._STATIC_MODELS, cls.default_model_id(), "elevenlabs_tts")
        return elevenlabs.TTS(
            api_key=api_key,
            voice_id=context.agent_voice_id or elevenlabs.DEFAULT_VOICE_ID,
            model=model,
        )
