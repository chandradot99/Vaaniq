"""STT provider implementations — importing this module registers all STT providers."""

from vaaniq.voice.providers.stt.deepgram import DeepgramSTTProvider
from vaaniq.voice.providers.stt.openai import OpenAISTTProvider
from vaaniq.voice.providers.stt.sarvam import SarvamSTTProvider

__all__ = ["DeepgramSTTProvider", "OpenAISTTProvider", "SarvamSTTProvider"]
