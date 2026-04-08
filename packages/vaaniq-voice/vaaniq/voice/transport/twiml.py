"""
TwiML response builders.

These return raw XML strings — FastAPI endpoints return them with
media_type="application/xml". Kept as plain string builders (no twilio SDK
dependency here) so they are easy to test without network access.
"""


def inbound_connect_twiml(websocket_url: str) -> str:
    """
    TwiML for inbound calls — tells Twilio to open a Media Stream WebSocket.

    Twilio will POST to our /webhooks/twilio/voice/inbound endpoint, and we
    return this response. Twilio then opens a persistent WebSocket to
    websocket_url where it will stream 8kHz mu-law audio both ways.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Connect>"
        f'<Stream url="{websocket_url}" />'
        "</Connect>"
        "</Response>"
    )


def outbound_connect_twiml(websocket_url: str) -> str:
    """
    TwiML for outbound calls — same as inbound once the call is answered.

    Twilio calls this URL when the dialled party picks up.
    """
    return inbound_connect_twiml(websocket_url)


def transfer_twiml(transfer_number: str, whisper: str | None = None) -> str:
    """
    TwiML for a warm transfer to a human agent.

    Args:
        transfer_number: E.164 phone number to dial, e.g. "+919876543210".
        whisper:         Optional message read to the agent before connecting
                         (the customer cannot hear this).
    """
    whisper_block = ""
    if whisper:
        whisper_block = f"<Say>{whisper}</Say>"

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Dial>{whisper_block}<Number>{transfer_number}</Number></Dial>"
        "</Response>"
    )


def hangup_twiml(message: str | None = None) -> str:
    """
    TwiML to say a farewell message (optional) then hang up.
    Used when the agent ends the session gracefully.
    """
    say_block = f"<Say>{message}</Say>" if message else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"{say_block}"
        "<Hangup />"
        "</Response>"
    )
