"""
SarvamTTS — custom LiveKit TTS plugin for Sarvam AI.

Sarvam Bulbul TTS supports 11 Indian languages with natural-sounding voices.
Uses Sarvam's REST API to synthesize speech and stream the audio back.

Docs: https://docs.sarvam.ai/api-reference-docs/text-to-speech
"""

from __future__ import annotations

import base64
from typing import Optional

import httpx
import structlog
from livekit.agents import tts, utils

log = structlog.get_logger()

_SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"

# Sarvam Bulbul voice IDs by language
_DEFAULT_VOICES: dict[str, str] = {
    "hi-IN": "meera",
    "ta-IN": "pavithra",
    "te-IN": "arvind",
    "bn-IN": "amartya",
    "gu-IN": "manisha",
    "kn-IN": "suresh",
    "ml-IN": "indu",
    "mr-IN": "aarohi",
    "pa-IN": "nirmal",
    "or-IN": "abhijit",
    "en-IN": "maya",
    "en-US": "maya",
}


class SarvamTTS(tts.TTS):
    """
    LiveKit TTS implementation backed by Sarvam AI Bulbul TTS.

    Synthesizes speech via Sarvam's REST API and buffers the audio for
    streaming to LiveKit's pipeline. Streaming is simulated by chunking
    the synthesized audio into frames.
    """

    def __init__(
        self,
        *,
        api_key: str,
        voice: Optional[str] = None,
        language: str = "hi-IN",
        speed: float = 1.0,
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=22050,
            num_channels=1,
        )
        self._api_key = api_key
        self._language = language
        self._voice = voice or _DEFAULT_VOICES.get(language, "meera")
        self._speed = speed

    def synthesize(
        self,
        text: str,
        *,
        conn_options: Optional[tts.APIConnectOptions] = None,
    ) -> tts.ChunkedStream:
        return SarvamChunkedStream(
            self,
            text=text,
            api_key=self._api_key,
            voice=self._voice,
            language=self._language,
            speed=self._speed,
        )


class SarvamChunkedStream(tts.ChunkedStream):
    """Synthesize speech via Sarvam REST API and stream the audio chunks."""

    def __init__(
        self,
        tts_instance: SarvamTTS,
        *,
        text: str,
        api_key: str,
        voice: str,
        language: str,
        speed: float,
    ) -> None:
        super().__init__(tts_instance, input_text=text)
        self._api_key = api_key
        self._voice = voice
        self._language = language
        self._speed = speed

    async def _run(self, max_retry: int = 3) -> None:
        payload = {
            "inputs": [self._input_text],
            "target_language_code": self._language,
            "speaker": self._voice,
            "pitch": 0,
            "pace": self._speed,
            "loudness": 1.5,
            "speech_sample_rate": 22050,
            "enable_preprocessing": True,
            "model": "bulbul:v1",
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_SARVAM_TTS_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # Sarvam returns base64-encoded WAV audio
        audio_b64 = data.get("audios", [""])[0]
        if not audio_b64:
            log.error("sarvam_tts_empty_response", text_preview=self._input_text[:40])
            return

        audio_bytes = base64.b64decode(audio_b64)

        # Strip WAV header (44 bytes) and emit raw PCM frames
        pcm = audio_bytes[44:]
        frame_size = 22050 * 2 * 20 // 1000  # 20ms at 22050Hz, 16-bit
        for i in range(0, len(pcm), frame_size):
            chunk = pcm[i:i + frame_size]
            if chunk:
                self._event_ch.send_nowait(
                    tts.SynthesizedAudio(
                        request_id=self._request_id,
                        segment_id=self._segment_id,
                        frame=utils.audio.AudioFrame(
                            data=chunk,
                            sample_rate=22050,
                            num_channels=1,
                            samples_per_channel=len(chunk) // 2,
                        ),
                    )
                )
