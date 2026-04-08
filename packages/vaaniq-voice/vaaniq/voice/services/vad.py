"""
Process-wide Silero VAD singleton.

Loading the Silero model takes ~100ms on first use (reads the ONNX file from
disk). If every call instantiates its own SileroVADAnalyzer, that 100ms is
paid by every caller. Instead, we load once at server startup and reuse the
same instance across all concurrent pipelines.

Usage:
    from vaaniq.voice.services.vad import get_vad_analyzer, preload_vad

    # At startup (voice server lifespan):
    await preload_vad()

    # Per call (pipeline builder):
    vad = get_vad_analyzer()

Note: Pipecat's SileroVADAnalyzer is thread-safe for concurrent reads — the
underlying ONNX model is stateless; only the per-frame audio buffer is
instance state. Each pipeline gets the same analyzer instance; Pipecat
internally uses per-pipeline buffers, so concurrent calls don't interfere.
"""

import structlog
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from vaaniq.voice.constants import (
    VAD_CONFIDENCE,
    VAD_MIN_VOLUME,
    VAD_START_SECS,
    VAD_STOP_SECS,
)

log = structlog.get_logger()

_vad: SileroVADAnalyzer | None = None


def get_vad_analyzer() -> SileroVADAnalyzer:
    """
    Return the process-wide VAD singleton, creating it on first call.
    Call preload_vad() at server startup to pay the ~100ms load cost upfront.
    """
    global _vad
    if _vad is None:
        log.info("vad_loading")
        _vad = SileroVADAnalyzer(
            params=VADParams(
                confidence=VAD_CONFIDENCE,
                start_secs=VAD_START_SECS,
                stop_secs=VAD_STOP_SECS,
                min_volume=VAD_MIN_VOLUME,
            )
        )
        log.info("vad_loaded")
    return _vad


async def preload_vad() -> None:
    """
    Pre-load the Silero VAD model at server startup so the first caller
    doesn't pay the ~100ms disk read cost.
    """
    get_vad_analyzer()
