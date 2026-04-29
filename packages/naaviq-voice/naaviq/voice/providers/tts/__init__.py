"""TTS provider implementations — importing this module registers all TTS providers."""

from naaviq.voice.providers.tts.cartesia import CartesiaTTSProvider
from naaviq.voice.providers.tts.elevenlabs import ElevenLabsTTSProvider
from naaviq.voice.providers.tts.openai import OpenAITTSProvider
from naaviq.voice.providers.tts.sarvam import SarvamTTSProvider

__all__ = ["CartesiaTTSProvider", "ElevenLabsTTSProvider", "OpenAITTSProvider", "SarvamTTSProvider"]
