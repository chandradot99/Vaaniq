"""STT provider implementations — importing this module registers all STT providers."""

from naaviq.voice.providers.stt.deepgram import DeepgramSTTProvider
from naaviq.voice.providers.stt.openai import OpenAISTTProvider
from naaviq.voice.providers.stt.sarvam import SarvamSTTProvider

__all__ = ["DeepgramSTTProvider", "OpenAISTTProvider", "SarvamSTTProvider"]
