"""
ElevenLabs TTS provider — wraps Pipecat's ElevenLabsTTSService.

Best for: voice cloning, highest quality, 32 languages.
Model: eleven_flash_v2_5 — 75ms TTFA, good quality, multilingual.
Alternative: eleven_turbo_v2_5 — 250ms TTFA, highest quality.

More expensive than Cartesia ($103 vs $46/1M chars) — use when
voice quality or voice cloning is required.
"""

from typing import Optional

from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from vaaniq.voice.constants import TWILIO_SAMPLE_RATE

_DEFAULT_MODEL = "eleven_flash_v2_5"   # fastest with good quality
_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel — ElevenLabs default


def create_elevenlabs_tts(
    api_key: str,
    voice_id: Optional[str] = None,
    model: Optional[str] = None,
    sample_rate: int = TWILIO_SAMPLE_RATE,
) -> ElevenLabsTTSService:
    """
    Create an ElevenLabsTTSService configured for VaaniQ's voice pipeline.

    Args:
        api_key:     ElevenLabs API key from org BYOK integrations.
        voice_id:    ElevenLabs voice ID. Falls back to Rachel (default voice).
        model:       ElevenLabs model. Defaults to "eleven_flash_v2_5".
        sample_rate: Output audio sample rate. Must match transport (8000 for Twilio).
    """
    return ElevenLabsTTSService(
        api_key=api_key,
        voice_id=voice_id or _DEFAULT_VOICE_ID,
        model=model or _DEFAULT_MODEL,
        sample_rate=sample_rate,
    )
