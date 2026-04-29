"""
Pydantic schemas for the voice API endpoints.
"""

from datetime import datetime
from typing import Any

from pydantic import field_validator
from naaviq.server.core.schemas import CustomModel


# ── Voice provider schemas ────────────────────────────────────────────────────

class ModelInfoResponse(CustomModel):
    id: str
    display_name: str
    description: str | None = None
    languages: list[str] = []
    is_default: bool = False
    streaming: bool = True
    category: str | None = None


class VoiceInfoResponse(CustomModel):
    id: str
    name: str
    preview_url: str | None = None
    gender: str | None = None
    language: str | None = None
    category: str | None = None
    description: str | None = None


class STTProviderResponse(CustomModel):
    provider_id: str
    display_name: str
    languages: list[str] = []


class TTSProviderResponse(CustomModel):
    provider_id: str
    display_name: str
    supports_voices: bool
    languages: list[str] = []

# ── Voice Config ──────────────────────────────────────────────────────────────

class VoiceConfig(CustomModel):
    """Per-pipeline voice settings. Null fields defer to org/platform defaults."""
    language: str | None = None        # BCP-47 e.g. "en-US", "hi-IN"
    stt_provider: str | None = None    # "deepgram" | "assemblyai" | None
    stt_model: str | None = None       # e.g. "nova-2", "nova-3"
    tts_provider: str | None = None    # "deepgram" | "cartesia" | "elevenlabs" | "azure" | None
    tts_voice_id: str | None = None    # provider-specific voice ID / name
    tts_model: str | None = None       # provider-specific model name
    tts_speed: float | None = None     # 0.5–2.0, None = provider default

    # ── Emotion / expressiveness controls ────────────────────────────────────
    # Cartesia: single emotion string e.g. "positivity:high", "curiosity:medium"
    tts_emotion: str | None = None
    # ElevenLabs: voice stability (0.0–1.0, higher = more consistent/monotone)
    tts_stability: float | None = None
    # ElevenLabs: style expressiveness (0.0–1.0, higher = more expressive)
    tts_style: float | None = None
    # OpenAI gpt-4o-mini-tts: free-form instruction e.g. "speak in a warm, friendly tone"
    tts_instructions: str | None = None


class UpdateVoiceConfigRequest(CustomModel):
    voice_config: VoiceConfig | None = None


class TTSPreviewRequest(CustomModel):
    tts_provider: str
    text: str
    voice_config: VoiceConfig | None = None


class UpdatePhoneNumberNameRequest(CustomModel):
    friendly_name: str | None = None


# ── Phone Numbers ─────────────────────────────────────────────────────────────

class AddPhoneNumberRequest(CustomModel):
    agent_id: str
    number: str                  # E.164 format: +14155551234
    provider: str = "twilio"     # "twilio" | "vonage" | "telnyx"
    sid: str = ""                # Provider SID (Twilio: PN...)
    friendly_name: str | None = None

    @field_validator("number")
    @classmethod
    def e164_format(cls, v: str) -> str:
        v = v.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not v.startswith("+") or not v[1:].isdigit() or len(v) < 8:
            raise ValueError("number must be in E.164 format, e.g. +14155551234")
        return v

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, v: str) -> str:
        allowed = {"twilio", "vonage", "telnyx"}
        if v not in allowed:
            raise ValueError(f"provider must be one of: {', '.join(allowed)}")
        return v


class TwilioAvailableNumber(CustomModel):
    """A Twilio number on the org's account that may or may not be imported yet."""
    number: str              # E.164 e.g. +14155551234
    sid: str                 # Twilio PhoneNumberSid (PN...)
    friendly_name: str | None
    capabilities: dict       # {"voice": true, "sms": true, "mms": false}
    already_imported: bool   # True if this org already has this number as a pipeline


class ReassignPhoneNumberRequest(CustomModel):
    agent_id: str


class PhoneNumberResponse(CustomModel):
    id: str
    org_id: str
    agent_id: str
    number: str
    provider: str
    sid: str
    friendly_name: str | None
    voice_config: VoiceConfig | None
    created_at: datetime


# ── Calls ─────────────────────────────────────────────────────────────────────

class OutboundCallRequest(CustomModel):
    agent_id: str
    from_number: str     # E.164 — one of the org's registered phone numbers
    to_number: str       # E.164 — the customer's phone number
    extra_context: dict[str, Any] = {}

    @field_validator("from_number", "to_number")
    @classmethod
    def e164_format(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("+") or not v[1:].isdigit() or len(v) < 8:
            raise ValueError("phone number must be in E.164 format, e.g. +14155551234")
        return v


class OutboundCallResponse(CustomModel):
    session_id: str
    call_sid: str        # Twilio CallSid — useful for tracking
    status: str          # "queued" | "initiated"


class CallResponse(CustomModel):
    id: str
    org_id: str
    agent_id: str
    channel: str
    user_id: str         # caller's phone number (inbound) or called number (outbound)
    status: str
    duration_seconds: int | None
    sentiment: str | None
    summary: str | None
    meta: dict[str, Any]
    created_at: datetime
    ended_at: datetime | None
