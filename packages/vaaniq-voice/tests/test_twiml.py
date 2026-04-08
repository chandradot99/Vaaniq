from vaaniq.voice.transport.twiml import (
    hangup_twiml,
    inbound_connect_twiml,
    outbound_connect_twiml,
    transfer_twiml,
)


def test_inbound_connect_contains_websocket_url():
    url = "wss://api.vaaniq.com/ws/voice/session-123"
    xml = inbound_connect_twiml(url)
    assert url in xml
    assert "<Connect>" in xml
    assert "<Stream" in xml
    assert xml.startswith("<?xml")


def test_outbound_connect_matches_inbound():
    url = "wss://api.vaaniq.com/ws/voice/session-456"
    assert outbound_connect_twiml(url) == inbound_connect_twiml(url)


def test_transfer_twiml_contains_number():
    xml = transfer_twiml("+919876543210")
    assert "+919876543210" in xml
    assert "<Dial>" in xml
    assert "<Number>" in xml


def test_transfer_twiml_with_whisper():
    xml = transfer_twiml("+919876543210", whisper="Customer wants to upgrade their plan.")
    assert "Customer wants to upgrade" in xml
    assert "<Say>" in xml


def test_hangup_twiml_no_message():
    xml = hangup_twiml()
    assert "<Hangup />" in xml
    assert "<Say>" not in xml


def test_hangup_twiml_with_message():
    xml = hangup_twiml("Thank you for calling. Goodbye!")
    assert "Thank you for calling" in xml
    assert "<Say>" in xml
    assert "<Hangup />" in xml
