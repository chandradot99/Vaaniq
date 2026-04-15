"""Sarvam AI TTS provider — static models and voices (no public API endpoints)."""

from __future__ import annotations

from vaaniq.voice.providers._helpers import extract_key
from vaaniq.voice.providers.base import ModelInfo, TTSProviderBase, VoiceInfo
from vaaniq.voice.providers.registry import ProviderRegistry


@ProviderRegistry.register_tts
class SarvamTTSProvider(TTSProviderBase):
    provider_id = "sarvam"
    display_name = "Sarvam AI"

    _STATIC_MODELS = [
        ModelInfo("bulbul:v3", "Bulbul v3", description="Latest. 35+ voices, improved naturalness.", languages=["hi-IN", "ta-IN", "te-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "or-IN", "en-IN"], is_default=True),
        ModelInfo("bulbul:v1", "Bulbul v1", description="Legacy model.", languages=["hi-IN", "ta-IN", "te-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "or-IN", "en-IN"]),
    ]

    # Sarvam voices grouped by gender. All voices work across all supported languages.
    _STATIC_VOICES = [
        # Female
        VoiceInfo("meera",   "Meera",   gender="female", language="hi-IN", category="premade"),
        VoiceInfo("pavithra","Pavithra", gender="female", language="ta-IN", category="premade"),
        VoiceInfo("priya",   "Priya",   gender="female", language="hi-IN", category="premade"),
        VoiceInfo("neha",    "Neha",    gender="female", language="hi-IN", category="premade"),
        VoiceInfo("maya",    "Maya",    gender="female", language="en-IN", category="premade"),
        VoiceInfo("indu",    "Indu",    gender="female", language="ml-IN", category="premade"),
        VoiceInfo("aarohi",  "Aarohi",  gender="female", language="mr-IN", category="premade"),
        VoiceInfo("manisha", "Manisha", gender="female", language="gu-IN", category="premade"),
        VoiceInfo("ritu",    "Ritu",    gender="female", language="hi-IN", category="premade"),
        VoiceInfo("pooja",   "Pooja",   gender="female", language="hi-IN", category="premade"),
        VoiceInfo("simran",  "Simran",  gender="female", language="pa-IN", category="premade"),
        VoiceInfo("kavya",   "Kavya",   gender="female", language="hi-IN", category="premade"),
        VoiceInfo("ishita",  "Ishita",  gender="female", language="hi-IN", category="premade"),
        VoiceInfo("shreya",  "Shreya",  gender="female", language="hi-IN", category="premade"),
        VoiceInfo("roopa",   "Roopa",   gender="female", language="kn-IN", category="premade"),
        # Male
        VoiceInfo("rahul",   "Rahul",   gender="male", language="hi-IN", category="premade"),
        VoiceInfo("rohan",   "Rohan",   gender="male", language="hi-IN", category="premade"),
        VoiceInfo("arvind",  "Arvind",  gender="male", language="te-IN", category="premade"),
        VoiceInfo("amartya", "Amartya", gender="male", language="bn-IN", category="premade"),
        VoiceInfo("suresh",  "Suresh",  gender="male", language="kn-IN", category="premade"),
        VoiceInfo("nirmal",  "Nirmal",  gender="male", language="pa-IN", category="premade"),
        VoiceInfo("abhijit", "Abhijit", gender="male", language="or-IN", category="premade"),
        VoiceInfo("amit",    "Amit",    gender="male", language="hi-IN", category="premade"),
        VoiceInfo("dev",     "Dev",     gender="male", language="hi-IN", category="premade"),
        VoiceInfo("varun",   "Varun",   gender="male", language="hi-IN", category="premade"),
        VoiceInfo("manan",   "Manan",   gender="male", language="hi-IN", category="premade"),
        VoiceInfo("kabir",   "Kabir",   gender="male", language="hi-IN", category="premade"),
    ]

    # Per-language default voice (used when no voice_id is set on the agent)
    _LANGUAGE_DEFAULTS: dict[str, str] = {
        "hi-IN": "meera",
        "ta-IN": "pavithra",
        "te-IN": "arvind",
        "bn-IN": "amartya",
        "gu-IN": "manisha",
        "kn-IN": "suresh",
        "ml-IN": "indu",
        "mr-IN": "aarohi",
        "pa-IN": "nirmal",
        "or-IN": "abhijit",
        "en-IN": "maya",
        "en-US": "maya",
    }

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        return cls._STATIC_MODELS

    @classmethod
    def supports_voices(cls) -> bool:
        return True

    @classmethod
    def static_voices(cls) -> list[VoiceInfo]:
        return cls._STATIC_VOICES

    # fetch_models() and fetch_voices() intentionally not overridden —
    # Sarvam has no public API endpoints for listing models or voices.

    @classmethod
    def default_model_id(cls) -> str:
        return "bulbul:v3"

    @classmethod
    def create_plugin(cls, context):
        from vaaniq.voice.tts.sarvam import SarvamTTS

        api_key = extract_key(context.org_keys, cls.provider_id)
        language = context.agent_language or "hi-IN"
        voice = context.agent_voice_id or cls._LANGUAGE_DEFAULTS.get(language, "meera")
        return SarvamTTS(api_key=api_key, voice=voice, language=language)
