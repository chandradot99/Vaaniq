"""
AssemblyAI STT provider — wraps Pipecat's AssemblyAISTTService.

Better semantic endpointing than Deepgram for complex conversational speech.
Trade-off: English-only (no Hindi/Hinglish). Use Deepgram for Indian languages.
"""

from pipecat.services.assemblyai.stt import AssemblyAISTTService

from vaaniq.voice.constants import TWILIO_SAMPLE_RATE


def create_assemblyai_stt(
    api_key: str,
    language: str = "en-US",  # AssemblyAI only supports English — language arg ignored
    sample_rate: int = TWILIO_SAMPLE_RATE,
) -> AssemblyAISTTService:
    """
    Create an AssemblyAISTTService configured for VaaniQ's voice pipeline.

    Args:
        api_key:     AssemblyAI API key from org BYOK integrations.
        language:    Accepted for API consistency but ignored — AssemblyAI is English-only.
        sample_rate: Input audio sample rate. Twilio sends 8kHz — do not change.
    """
    return AssemblyAISTTService(
        api_key=api_key,
        vad_force_turn_endpoint=True,  # force turn endpoint on VAD silence
        sample_rate=sample_rate,
    )
