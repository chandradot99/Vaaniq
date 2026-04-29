from datetime import datetime
from typing import Any

from pydantic import field_validator

from naaviq.server.agents.constants import SUPPORTED_LANGUAGES
from naaviq.server.core.schemas import CustomModel
from naaviq.server.voice.schemas import VoiceConfig


class CreateAgentRequest(CustomModel):
    name: str
    system_prompt: str = ""
    voice_id: str | None = None
    language: str = "en"
    simple_mode: bool = True
    graph_config: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Agent name cannot be empty")
        return v.strip()

    @field_validator("language")
    @classmethod
    def valid_language(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language. Supported: {SUPPORTED_LANGUAGES}")
        return v


class UpdateAgentRequest(CustomModel):
    name: str | None = None
    system_prompt: str | None = None
    voice_id: str | None = None
    language: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Agent name cannot be empty")
        return v.strip() if v else v

    @field_validator("language")
    @classmethod
    def valid_language(cls, v: str | None) -> str | None:
        if v is not None and v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language. Supported: {SUPPORTED_LANGUAGES}")
        return v


class UpdateGraphRequest(CustomModel):
    graph_config: dict[str, Any]

    @field_validator("graph_config")
    @classmethod
    def has_entry_point(cls, v: dict) -> dict:
        if "entry_point" not in v:
            raise ValueError("graph_config must have an 'entry_point'")
        if "nodes" not in v:
            raise ValueError("graph_config must have a 'nodes' list")
        return v


class VoicePreviewResponse(CustomModel):
    """Returned by POST /v1/agents/{agent_id}/voice-preview."""
    session_id: str          # The preview session ID (for debugging / transcript lookup)
    room_name: str           # LiveKit room name the browser should join
    token: str               # LiveKit participant token — pass to livekit-client
    livekit_url: str         # WebSocket URL for the LiveKit server


class AgentResponse(CustomModel):
    id: str
    org_id: str
    name: str
    system_prompt: str
    voice_id: str | None
    voice_config: VoiceConfig | None
    language: str
    simple_mode: bool
    graph_config: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class UpdateVoiceConfigRequest(CustomModel):
    voice_config: VoiceConfig | None = None
