from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VoiceCallContext:
    """
    Immutable snapshot of everything the pipeline needs at call start.
    Resolved once at WebSocket connect time; passed into pipeline builder.

    Rule: all fields without defaults must come before fields with defaults
    (Python dataclass requirement).
    """

    # ── Required fields (no defaults) ────────────────────────────────────────
    # Session / identity
    session_id: str
    org_id: str
    agent_id: str

    # Agent config
    agent_language: str               # e.g. "en-US", "hi-IN"
    graph_config: dict                # raw graph_config JSON from agents table
    graph_version: int                # incremented on every graph publish — cache key
    initial_messages: list            # system prompt formatted as OpenAI messages

    # BYOK keys (Fernet-decrypted at session start)
    org_keys: dict

    # ── Optional fields (with defaults) ──────────────────────────────────────
    # Telephony provider
    telephony_provider: str = "twilio"  # "twilio" | "vonage" | "telnyx"

    # Call identifiers (provider-agnostic names; populated by context_builder)
    call_sid: str = ""
    stream_sid: str = ""              # set after the provider sends the 'start' message
    from_number: str = ""             # caller's phone number
    to_number: str = ""               # org's number

    # Twilio-specific credentials (present when telephony_provider == "twilio")
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    # Resolved provider names (from org integrations, with fallback to platform defaults)
    stt_provider: str = "deepgram"
    stt_model: Optional[str] = None       # None = provider default
    tts_provider: str = "cartesia"
    tts_model: Optional[str] = None       # None = provider default
    tts_speed: Optional[float] = None     # None = provider default
    agent_voice_id: Optional[str] = None

    # Call direction
    direction: str = "inbound"        # "inbound" | "outbound"

    # Optional context injected for outbound calls
    extra_context: dict = field(default_factory=dict)
