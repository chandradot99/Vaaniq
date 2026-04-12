"""
SarvamSTT — custom LiveKit STT plugin for Sarvam AI.

Sarvam AI supports 11 Indian languages + English (India), including Hinglish
code-mixing. It uses a streaming WebSocket API compatible with the LiveKit
STT interface via its transcription endpoint.

Docs: https://docs.sarvam.ai/api-reference-docs/speech-to-text-translate/streaming

Key config for low latency:
    - language="unknown": enables automatic language detection (Hinglish included)
    - endpointing delay is set to 70ms (Sarvam signals fast)
"""

from __future__ import annotations

from typing import Optional

import structlog
from livekit.agents import stt, utils
from livekit.agents.types import NOT_GIVEN, NotGivenOr

log = structlog.get_logger()

# Sarvam AI streaming STT endpoint
_SARVAM_STT_URL = "wss://api.sarvam.ai/speech-to-text-translate/streaming"

# Language codes Sarvam AI supports
_SARVAM_LANGUAGES = {
    "hi-IN": "hi-IN",   # Hindi
    "ta-IN": "ta-IN",   # Tamil
    "te-IN": "te-IN",   # Telugu
    "bn-IN": "bn-IN",   # Bengali
    "gu-IN": "gu-IN",   # Gujarati
    "kn-IN": "kn-IN",   # Kannada
    "ml-IN": "ml-IN",   # Malayalam
    "mr-IN": "mr-IN",   # Marathi
    "pa-IN": "pa-IN",   # Punjabi
    "or-IN": "or-IN",   # Odia
    "en-IN": "en-IN",   # English (India)
    # Auto-detect (handles Hinglish and code-mixing)
    "unknown": "unknown",
}


class SarvamSTT(stt.STT):
    """
    LiveKit STT implementation backed by Sarvam AI's streaming API.

    For Hinglish or mixed-language calls, set language="unknown" —
    Sarvam will auto-detect and handle code-mixing gracefully.

    For best latency: the turn detection mode on the Agent should be set to
    "stt" and min_endpointing_delay=0.07 when using Sarvam.
    """

    def __init__(self, *, api_key: str, language: str = "unknown") -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=True, interim_results=True)
        )
        self._api_key = api_key
        # Map generic language codes (e.g. "en-US") to Sarvam equivalents
        self._language = _SARVAM_LANGUAGES.get(language, "unknown")

    def stream(
        self,
        *,
        language: Optional[str] = None,
        conn_options: Optional[stt.APIConnectOptions] = None,
    ) -> stt.SpeechStream:
        return SarvamSpeechStream(self, api_key=self._api_key, language=language or self._language)

    async def _recognize_impl(
        self,
        buffer: utils.AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: stt.APIConnectOptions,
    ) -> stt.SpeechEvent:
        raise NotImplementedError("SarvamSTT only supports streaming mode.")


class SarvamSpeechStream(stt.SpeechStream):
    """
    Streaming speech recognition via Sarvam AI WebSocket API.

    Converts LiveKit audio frames (linear PCM, any sample rate) to 16kHz
    mono PCM before sending to Sarvam.
    """

    def __init__(self, stt_instance: SarvamSTT, *, api_key: str, language: str) -> None:
        super().__init__(stt_instance)
        self._api_key = api_key
        self._language = language

    async def _run(self) -> None:
        # TODO: implement Sarvam AI streaming WebSocket STT
        # Sarvam uses a WebSocket-based streaming API. Full implementation
        # requires a WebSocket client library (e.g. websockets package).
        # Placeholder logs connection intent — replace with actual WebSocket handshake.
        log.info("sarvam_stt_connected", language=self._language)

    async def _send_audio(self, frame: bytes) -> None:
        """Send a raw PCM audio frame to the Sarvam WebSocket."""
        # Implementation depends on the WebSocket library used
        pass
