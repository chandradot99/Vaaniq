"""
Deepgram Aura TTS provider — wraps Pipecat's DeepgramTTSService (WebSocket).

Same API key covers both Deepgram STT and TTS — one key, one account.
Best for: testing (generous $200 free credit), low latency, good quality.
Model: aura-2-helena-en (default) — natural US English female voice.

Uses WebSocket streaming (DeepgramTTSService) rather than HTTP — lower latency
and no external aiohttp session required.

Other available voices:
  aura-2-arcas-en    — male, neutral
  aura-2-luna-en     — female, conversational
  aura-2-orion-en    — male, professional
  Full list: https://developers.deepgram.com/docs/tts-models
"""

from typing import Optional

from pipecat.services.deepgram.tts import DeepgramTTSService
from vaaniq.voice.constants import TWILIO_SAMPLE_RATE

_DEFAULT_VOICE = "aura-2-helena-en"


def create_deepgram_tts(
    api_key: str,
    voice_id: Optional[str] = None,
    sample_rate: int = TWILIO_SAMPLE_RATE,
) -> DeepgramTTSService:
    """
    Create a DeepgramTTSService (WebSocket) configured for VaaniQ's voice pipeline.

    Args:
        api_key:     Deepgram API key — same key used for STT.
        voice_id:    Deepgram Aura voice name. Falls back to aura-2-helena-en.
        sample_rate: Output audio sample rate. Must match transport (8000 for Twilio).
    """
    return DeepgramTTSService(
        api_key=api_key,
        voice=voice_id or _DEFAULT_VOICE,
        sample_rate=sample_rate,
    )
