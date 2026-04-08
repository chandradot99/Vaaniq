"""
Azure AI Speech TTS provider — wraps Pipecat's AzureTTSService.

Best for: Indian languages (Hindi, Tamil, Telugu, Marathi) and 140+ locales.
Cheapest at scale ($15/1M chars vs $46 Cartesia, $103 ElevenLabs).

Language → voice mapping for Indian languages:
  hi-IN  → hi-IN-SwaraNeural   (female, natural Hindi)
  ta-IN  → ta-IN-PallaviNeural (female, natural Tamil)
  te-IN  → te-IN-ShrutiNeural  (female, natural Telugu)
  en-IN  → en-IN-NeerjaNeural  (female, Indian English)
  mr-IN  → mr-IN-AarohiNeural  (female, Marathi)
"""

from typing import Optional

from pipecat.services.azure.tts import AzureTTSService
from vaaniq.voice.constants import TWILIO_SAMPLE_RATE

# Language → recommended Azure neural voice
_LANGUAGE_VOICE_MAP: dict[str, str] = {
    "hi-IN": "hi-IN-SwaraNeural",
    "ta-IN": "ta-IN-PallaviNeural",
    "te-IN": "te-IN-ShrutiNeural",
    "en-IN": "en-IN-NeerjaNeural",
    "mr-IN": "mr-IN-AarohiNeural",
    "en-US": "en-US-SaraNeural",
    "en-GB": "en-GB-SoniaNeural",
}

_DEFAULT_REGION = "eastus"


def create_azure_tts(
    api_key: str,
    voice_id: Optional[str] = None,
    language: str = "en-US",
    region: Optional[str] = None,
    sample_rate: int = TWILIO_SAMPLE_RATE,
) -> AzureTTSService:
    """
    Create an AzureTTSService configured for VaaniQ's voice pipeline.

    Args:
        api_key:     Azure Cognitive Services key from org BYOK integrations.
        voice_id:    Azure voice name. Auto-selected from language if not provided.
        language:    BCP-47 language tag — used to pick the best voice automatically.
        region:      Azure region, e.g. "eastus". Falls back to "eastus" default.
        sample_rate: Output audio sample rate. Must match transport (8000 for Twilio).
    """
    # Auto-select voice based on language if no explicit voice provided
    chosen_voice = voice_id or _LANGUAGE_VOICE_MAP.get(language, "en-US-SaraNeural")
    chosen_region = region or _DEFAULT_REGION

    return AzureTTSService(
        api_key=api_key,
        region=chosen_region,
        voice=chosen_voice,
        sample_rate=sample_rate,
    )
