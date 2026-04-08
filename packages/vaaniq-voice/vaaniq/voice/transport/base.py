"""
Telephony transport factory.

Resolves the org's telephony provider to a configured Pipecat transport.
All providers share the same factory interface so the pipeline builder
doesn't need to know which provider is in use.

Adding a new provider:
  1. Create vaaniq/voice/transport/<provider>.py with a build_<provider>_transport(websocket, context) function.
  2. Register it in _build_registry() below.
  3. Add the provider name to vaaniq-server's context_builder telephony resolution logic.
  4. Add any provider-specific credential fields to VoiceCallContext.

Supported providers:
  twilio    — FastAPIWebsocketTransport + TwilioFrameSerializer (8kHz mu-law)
  vonage    — (future) NexmoWebsocketTransport
  telnyx    — (future) TelnyxWebsocketTransport
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from vaaniq.voice.exceptions import ProviderNotFoundError

if TYPE_CHECKING:
    from vaaniq.voice.pipeline.context import VoiceCallContext


def _build_registry() -> dict[str, Callable]:
    from vaaniq.voice.transport.twilio import build_twilio_transport

    return {
        "twilio": build_twilio_transport,
    }


def create_transport(websocket, context: VoiceCallContext) -> Any:
    """
    Resolve and instantiate a telephony transport from the registry.

    Args:
        websocket: The FastAPI WebSocket object for this call.
        context:   Fully resolved VoiceCallContext — the factory extracts
                   provider-specific credentials from it.

    Raises:
        ProviderNotFoundError: If context.telephony_provider is not registered.
    """
    registry = _build_registry()
    provider = context.telephony_provider

    if provider not in registry:
        raise ProviderNotFoundError("transport", provider)

    return registry[provider](websocket, context)
