"""Sarvam AI TTS provider — static models and voices (no public API endpoints)."""

from __future__ import annotations

from naaviq.voice.providers._helpers import extract_key
from naaviq.voice.providers.base import ModelInfo, TTSProviderBase, VoiceInfo
from naaviq.voice.providers.registry import ProviderRegistry

_SARVAM_LANGS = [
    "hi-IN", "ta-IN", "te-IN", "bn-IN", "gu-IN",
    "kn-IN", "ml-IN", "mr-IN", "pa-IN", "or-IN", "en-IN",
]


@ProviderRegistry.register_tts
class SarvamTTSProvider(TTSProviderBase):
    provider_id = "sarvam"
    display_name = "Sarvam AI"
    languages = _SARVAM_LANGS

    _STATIC_MODELS = [
        ModelInfo(
            "bulbul:v3",
            "Bulbul v3",
            description="Latest. 30+ voices, best naturalness for Indian languages.",
            languages=_SARVAM_LANGS,
            is_default=True,
            streaming=True,
        ),
        ModelInfo(
            "bulbul:v2",
            "Bulbul v2",
            description="Previous generation. 7 voices.",
            languages=_SARVAM_LANGS,
            is_default=False,
            streaming=True,
        ),
    ]

    # bulbul:v3 voices — 30 voices, shubh is default
    _VOICES_V3 = [
        # Female
        VoiceInfo("meera",    "Meera",    gender="female", language="hi-IN", category="premade"),
        VoiceInfo("pavithra", "Pavithra", gender="female", language="ta-IN", category="premade"),
        VoiceInfo("priya",    "Priya",    gender="female", language="hi-IN", category="premade"),
        VoiceInfo("neha",     "Neha",     gender="female", language="hi-IN", category="premade"),
        VoiceInfo("maya",     "Maya",     gender="female", language="en-IN", category="premade"),
        VoiceInfo("indu",     "Indu",     gender="female", language="ml-IN", category="premade"),
        VoiceInfo("aarohi",   "Aarohi",   gender="female", language="mr-IN", category="premade"),
        VoiceInfo("manisha",  "Manisha",  gender="female", language="gu-IN", category="premade"),
        VoiceInfo("ritu",     "Ritu",     gender="female", language="hi-IN", category="premade"),
        VoiceInfo("pooja",    "Pooja",    gender="female", language="hi-IN", category="premade"),
        VoiceInfo("simran",   "Simran",   gender="female", language="pa-IN", category="premade"),
        VoiceInfo("kavya",    "Kavya",    gender="female", language="hi-IN", category="premade"),
        VoiceInfo("ishita",   "Ishita",   gender="female", language="hi-IN", category="premade"),
        VoiceInfo("shreya",   "Shreya",   gender="female", language="hi-IN", category="premade"),
        VoiceInfo("roopa",    "Roopa",    gender="female", language="kn-IN", category="premade"),
        # Male
        VoiceInfo("shubh",    "Shubh",    gender="male",   language="hi-IN", category="premade"),
        VoiceInfo("rahul",    "Rahul",    gender="male",   language="hi-IN", category="premade"),
        VoiceInfo("rohan",    "Rohan",    gender="male",   language="hi-IN", category="premade"),
        VoiceInfo("arvind",   "Arvind",   gender="male",   language="te-IN", category="premade"),
        VoiceInfo("amartya",  "Amartya",  gender="male",   language="bn-IN", category="premade"),
        VoiceInfo("suresh",   "Suresh",   gender="male",   language="kn-IN", category="premade"),
        VoiceInfo("nirmal",   "Nirmal",   gender="male",   language="pa-IN", category="premade"),
        VoiceInfo("abhijit",  "Abhijit",  gender="male",   language="or-IN", category="premade"),
        VoiceInfo("amit",     "Amit",     gender="male",   language="hi-IN", category="premade"),
        VoiceInfo("dev",      "Dev",      gender="male",   language="hi-IN", category="premade"),
        VoiceInfo("varun",    "Varun",    gender="male",   language="hi-IN", category="premade"),
        VoiceInfo("manan",    "Manan",    gender="male",   language="hi-IN", category="premade"),
        VoiceInfo("kabir",    "Kabir",    gender="male",   language="hi-IN", category="premade"),
    ]

    # bulbul:v2 voices — 7 voices, anushka is default
    _VOICES_V2 = [
        VoiceInfo("anushka",  "Anushka",  gender="female", language="hi-IN", category="premade"),
        VoiceInfo("manisha",  "Manisha",  gender="female", language="hi-IN", category="premade"),
        VoiceInfo("vidya",    "Vidya",    gender="female", language="hi-IN", category="premade"),
        VoiceInfo("arjun",    "Arjun",    gender="male",   language="hi-IN", category="premade"),
        VoiceInfo("abhijit",  "Abhijit",  gender="male",   language="hi-IN", category="premade"),
        VoiceInfo("amol",     "Amol",     gender="male",   language="hi-IN", category="premade"),
        VoiceInfo("amartya",  "Amartya",  gender="male",   language="bn-IN", category="premade"),
    ]

    # Per-language default voice for bulbul:v3 (used when no voice_id is set)
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
        # Return v3 voices as the default list (v3 is the default model)
        return cls._VOICES_V3

    # fetch_models() and fetch_voices() intentionally not overridden —
    # Sarvam has no public API endpoints for listing models or voices.

    @classmethod
    def default_model_id(cls) -> str:
        return "bulbul:v3"

    @classmethod
    def create_plugin(cls, context):
        from naaviq.voice.tts.sarvam import SarvamTTS

        api_key = extract_key(context.org_keys, cls.provider_id)
        language = context.agent_language or "hi-IN"
        voice = context.agent_voice_id or cls._LANGUAGE_DEFAULTS.get(language, "meera")
        return SarvamTTS(api_key=api_key, voice=voice, language=language)
