"""
Deepgram STT provider — wraps Pipecat's DeepgramSTTService.

Default model: Nova-3 — best WER (5.26%) at <300ms latency for voice agents.
Alternative: Flux — model-integrated turn detection (replaces need for SmartTurn).

Twilio PSTN audio is 8kHz mono mu-law. Deepgram accepts it natively.
"""

from typing import Optional

from deepgram import LiveOptions
from deepgram.audio.microphone import Microphone  # noqa: F401 — triggers SDK validation
from pipecat.services.deepgram.stt import DeepgramSTTService
from vaaniq.voice.constants import DEEPGRAM_ENDPOINTING_MS, TWILIO_SAMPLE_RATE

# Default model — best WER (5.26%) at <300ms latency for voice agents.
_DEFAULT_MODEL = "nova-3"

# Models that support turn detection natively (no separate SmartTurn needed).
_TURN_DETECTION_MODELS = {"flux", "nova-3-turbo"}


def create_deepgram_stt(
    api_key: str,
    language: str = "en-US",
    model: Optional[str] = None,
    sample_rate: int = TWILIO_SAMPLE_RATE,
) -> DeepgramSTTService:
    """
    Create a DeepgramSTTService configured for VaaniQ's voice pipeline.

    Args:
        api_key:     Deepgram API key from org BYOK integrations.
        language:    BCP-47 language tag, e.g. "en-US", "hi-IN", "en-IN".
                     "en-IN" is recommended for Indian English / Hinglish.
        model:       Deepgram model name. Defaults to nova-3.
        sample_rate: Input audio sample rate. Twilio sends 8kHz — do not change.
    """
    chosen_model = model or _DEFAULT_MODEL

    live_options = LiveOptions(
        model=chosen_model,
        language=language,
        smart_format=True,    # normalise numbers, dates, punctuation
        punctuate=True,
        # TwilioFrameSerializer converts Twilio mu-law → linear16 PCM before
        # producing AudioRawFrame, so Deepgram receives linear16, not mu-law.
        encoding="linear16",
        channels=1,
        sample_rate=sample_rate,
        # endpointing must be < VAD_STOP_SECS * 1000 so the final transcript
        # arrives in the aggregator before VAD closes the user turn.
        endpointing=DEEPGRAM_ENDPOINTING_MS,
        interim_results=True,  # partial transcripts for faster perceived response
    )

    return DeepgramSTTService(
        api_key=api_key,
        live_options=live_options,
        sample_rate=sample_rate,
    )
