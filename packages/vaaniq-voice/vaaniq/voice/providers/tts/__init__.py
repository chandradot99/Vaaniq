"""TTS provider implementations — importing this module registers all TTS providers."""

from vaaniq.voice.providers.tts.cartesia import CartesiaTTSProvider
from vaaniq.voice.providers.tts.elevenlabs import ElevenLabsTTSProvider
from vaaniq.voice.providers.tts.openai import OpenAITTSProvider
from vaaniq.voice.providers.tts.sarvam import SarvamTTSProvider

__all__ = ["CartesiaTTSProvider", "ElevenLabsTTSProvider", "OpenAITTSProvider", "SarvamTTSProvider"]
