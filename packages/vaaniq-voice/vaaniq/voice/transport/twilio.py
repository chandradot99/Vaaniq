"""
Twilio WebSocket transport.

Wraps Pipecat's FastAPIWebsocketTransport + TwilioFrameSerializer.
Called by the transport factory in transport/base.py — do not import directly
from pipeline code; use create_transport() instead.

Audio: 8kHz mono mu-law (Twilio PSTN hard constraint).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vaaniq.voice.pipeline.context import VoiceCallContext


def build_twilio_transport(websocket, context: VoiceCallContext):
    """
    Create a Pipecat FastAPIWebsocketTransport for a Twilio Media Stream.

    Reads credentials from context.twilio_account_sid / twilio_auth_token.
    Pipecat is imported lazily so tests can import this module without a
    full Pipecat install.
    """
    from pipecat.serializers.twilio import TwilioFrameSerializer
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )

    return FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=TwilioFrameSerializer(
                stream_sid=context.stream_sid,
                account_sid=context.twilio_account_sid,
                auth_token=context.twilio_auth_token,
                call_sid=context.call_sid,
            ),
        ),
    )
