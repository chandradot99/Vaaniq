"""
Voice pipeline constants — single source of truth for all magic numbers.

Changing a value here propagates to every provider, the pipeline builder,
and the task runner automatically.

Rules:
  - TWILIO_SAMPLE_RATE is a hard constraint from Twilio's PSTN spec — only
    change if switching to a non-Twilio transport.
  - VAD constants are tuned for natural conversational speech. Lowering
    VAD_STOP_SECS reduces latency but risks splitting mid-sentence turns.
  - DEEPGRAM_ENDPOINTING_MS must always be < VAD_STOP_SECS * 1000 so
    Deepgram's final transcript arrives before the VAD aggregator closes
    the turn — otherwise the aggregator fires with an empty buffer.
"""

# ── Audio ─────────────────────────────────────────────────────────────────────

# Twilio PSTN hard constraint: 8kHz mono mu-law.
# TwilioFrameSerializer converts to linear16 PCM before sending to STT.
TWILIO_SAMPLE_RATE: int = 8_000

# ── VAD (Voice Activity Detection — Silero) ───────────────────────────────────

# Minimum speech probability to treat audio as speech (0.0–1.0).
VAD_CONFIDENCE: float = 0.7

# Seconds of speech required before declaring user started talking.
VAD_START_SECS: float = 0.2

# Seconds of silence after speech before declaring user stopped talking.
# Must remain > DEEPGRAM_ENDPOINTING_MS / 1000 (currently 100ms).
VAD_STOP_SECS: float = 0.35

# Minimum audio volume level to treat as speech (0.0–1.0).
VAD_MIN_VOLUME: float = 0.6

# ── STT ───────────────────────────────────────────────────────────────────────

# Deepgram endpointing: milliseconds of silence before Deepgram finalises
# a transcript. Must be strictly less than VAD_STOP_SECS * 1000 (350ms).
DEEPGRAM_ENDPOINTING_MS: int = 100

# ── Pipeline lifecycle ────────────────────────────────────────────────────────

# Seconds without a BotSpeakingFrame or UserSpeakingFrame before Pipecat
# marks the pipeline idle and cancels it. After session_ended the Twilio
# WebSocket may linger; this bound ensures finalization runs promptly.
#
# 30s gives collect_data flows enough headroom: each field takes ~5-8s
# (LLM extraction call + re-ask) so a 6-field form needs up to ~50s.
# The previous 10s was too aggressive for multi-field voice collection.
PIPELINE_IDLE_TIMEOUT_SECS: float = 30.0

# Seconds to wait for the pipeline runner to flush cleanly before force-
# cancelling it in the finally block of run_voice_pipeline().
PIPELINE_SHUTDOWN_TIMEOUT_SECS: float = 2.0
