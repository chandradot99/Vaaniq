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

import asyncio
import json
from typing import Optional

import numpy as np
import structlog
from livekit.agents import stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, NotGivenOr

log = structlog.get_logger()

# Sarvam AI streaming STT endpoint
_SARVAM_STT_URL = "wss://api.sarvam.ai/speech-to-text-translate/streaming"

# Target sample rate required by Sarvam AI
_TARGET_SAMPLE_RATE = 16000

# Language codes Sarvam AI supports
_SARVAM_LANGUAGES = {
    "hi-IN": "hi-IN",  # Hindi
    "ta-IN": "ta-IN",  # Tamil
    "te-IN": "te-IN",  # Telugu
    "bn-IN": "bn-IN",  # Bengali
    "gu-IN": "gu-IN",  # Gujarati
    "kn-IN": "kn-IN",  # Kannada
    "ml-IN": "ml-IN",  # Malayalam
    "mr-IN": "mr-IN",  # Marathi
    "pa-IN": "pa-IN",  # Punjabi
    "or-IN": "or-IN",  # Odia
    "en-IN": "en-IN",  # English (India)
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
        conn_options: stt.APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechStream:
        return SarvamSpeechStream(
            stt_instance=self,
            conn_options=conn_options,
            api_key=self._api_key,
            language=language or self._language,
        )

    async def _recognize_impl(
        self,
        buffer,
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

    def __init__(
        self,
        stt_instance: SarvamSTT,
        *,
        conn_options: stt.APIConnectOptions,
        api_key: str,
        language: str,
    ) -> None:
        super().__init__(stt=stt_instance, conn_options=conn_options)
        self._api_key = api_key
        self._language = language

    async def _run(self) -> None:
        from websockets.asyncio.client import connect

        url = (
            f"{_SARVAM_STT_URL}"
            f"?language_code={self._language}&model=saarika:v2&sample_rate={_TARGET_SAMPLE_RATE}"
        )
        connect_headers = {"api-subscription-key": self._api_key}

        log.info("sarvam_stt_connecting", language=self._language)

        async with connect(url, additional_headers=connect_headers) as ws:
            log.info("sarvam_stt_connected", language=self._language)

            send_task = asyncio.create_task(self._send_loop(ws))
            recv_task = asyncio.create_task(self._recv_loop(ws))
            try:
                await asyncio.gather(send_task, recv_task)
            except Exception:
                send_task.cancel()
                recv_task.cancel()
                await asyncio.gather(send_task, recv_task, return_exceptions=True)
                raise

    async def _send_loop(self, ws) -> None:
        """Read audio frames from LiveKit input channel, send as PCM to Sarvam."""
        try:
            async for item in self._input_ch:
                if isinstance(item, stt.SpeechStream._FlushSentinel):
                    # Sarvam uses VAD internally — no flush signal needed
                    continue
                # item is rtc.AudioFrame — resample to 16kHz mono PCM
                pcm = _resample_to_16khz_mono(item)
                await ws.send(pcm)
        finally:
            # Empty frame signals end of audio to Sarvam
            try:
                await ws.send(b"")
            except Exception:
                pass

    async def _recv_loop(self, ws) -> None:
        """Receive transcripts from Sarvam WebSocket and emit SpeechEvents."""
        async for message in ws:
            if isinstance(message, bytes):
                continue
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                log.warning("sarvam_stt_invalid_json", message=message)
                continue

            transcript = data.get("transcript", "")
            if not transcript:
                continue

            is_final = data.get("is_final", True)
            event_type = (
                stt.SpeechEventType.FINAL_TRANSCRIPT
                if is_final
                else stt.SpeechEventType.INTERIM_TRANSCRIPT
            )
            self._event_ch.send_nowait(
                stt.SpeechEvent(
                    type=event_type,
                    alternatives=[
                        stt.SpeechData(language=self._language, text=transcript)
                    ],
                )
            )
            log.debug(
                "sarvam_stt_transcript",
                text=transcript,
                is_final=is_final,
                language=self._language,
            )


def _resample_to_16khz_mono(frame) -> bytes:
    """
    Convert a LiveKit AudioFrame to 16kHz mono 16-bit PCM bytes.

    Sarvam AI requires 16kHz, mono, 16-bit PCM. LiveKit delivers frames at
    the sample rate of the source (8kHz for PSTN, 48kHz for WebRTC).
    """
    samples = np.frombuffer(bytes(frame.data), dtype=np.int16)
    num_channels = frame.num_channels
    sample_rate = frame.sample_rate

    # Reshape to (samples_per_channel, num_channels)
    if num_channels > 1:
        samples = samples.reshape(-1, num_channels)
        # Mix to mono by averaging channels
        samples = samples.mean(axis=1).astype(np.int16)
    # else: already mono, shape is (N,)

    # Resample to 16kHz using linear interpolation
    if sample_rate != _TARGET_SAMPLE_RATE:
        n_in = len(samples)
        n_out = int(n_in * _TARGET_SAMPLE_RATE / sample_rate)
        x_in = np.linspace(0, n_in - 1, n_in)
        x_out = np.linspace(0, n_in - 1, n_out)
        samples = np.interp(x_out, x_in, samples).astype(np.int16)

    return samples.tobytes()
