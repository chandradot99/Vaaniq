from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VoiceCallContext:
    """
    Immutable snapshot of everything the voice agent needs at call start.
    Resolved once per call by context_builder.py and passed to the LiveKit
    worker which runs the agent in the room.

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

    # Call identifiers
    call_sid: str = ""                # Twilio CallSid (for status lookups)
    from_number: str = ""             # caller's phone number
    to_number: str = ""               # org's number (the dialled number)

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

    # Emotion / expressiveness controls (provider-specific, set via voice_config)
    tts_emotion: Optional[str] = None        # Cartesia: e.g. "positivity:high"
    tts_stability: Optional[float] = None    # ElevenLabs: 0.0–1.0
    tts_style: Optional[float] = None        # ElevenLabs: 0.0–1.0
    tts_instructions: Optional[str] = None   # OpenAI gpt-4o-mini-tts: free-form

    # Call direction
    direction: str = "inbound"        # "inbound" | "outbound"

    # Optional context injected for outbound calls
    extra_context: dict = field(default_factory=dict)
