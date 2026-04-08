"""
Cartesia TTS provider — wraps Pipecat's CartesiaTTSService.

Default: Sonic-3 — 90ms TTFA, high quality.
Lowest latency option: Sonic Turbo — 40ms TTFA (pass model="sonic-turbo").

Built on State Space Models (SSM) — O(n) complexity gives it the latency edge
over transformer-based TTS at streaming synthesis.
"""

from typing import Optional

from pipecat.services.cartesia.tts import CartesiaTTSService
from vaaniq.voice.constants import TWILIO_SAMPLE_RATE

# Cartesia's default voice — neutral English
_DEFAULT_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"
_DEFAULT_MODEL = "sonic-3"


def create_cartesia_tts(
    api_key: str,
    voice_id: Optional[str] = None,
    model: Optional[str] = None,
    sample_rate: int = TWILIO_SAMPLE_RATE,
) -> CartesiaTTSService:
    """
    Create a CartesiaTTSService configured for VaaniQ's voice pipeline.

    Args:
        api_key:     Cartesia API key from org BYOK integrations.
        voice_id:    Cartesia voice ID. Falls back to a neutral English voice.
        model:       Cartesia model. "sonic-3" (default) or "sonic-turbo" (lowest latency).
        sample_rate: Output audio sample rate. Must match transport (8000 for Twilio).
    """
    return CartesiaTTSService(
        api_key=api_key,
        voice_id=voice_id or _DEFAULT_VOICE_ID,
        model=model or _DEFAULT_MODEL,
        sample_rate=sample_rate,
        encoding="pcm_s16le",
        container="raw",
        # aggregate_sentences=True keeps default — full sentence gives cleaner prosody
        # vs token-by-token which has more artifacts. ~15ms cost, worth it.
    )
