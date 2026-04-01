from datetime import datetime
from typing import Any
from pydantic import field_validator
from vaaniq.server.core.schemas import CustomModel
from vaaniq.server.agents.constants import SUPPORTED_LANGUAGES


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


class AgentResponse(CustomModel):
    id: str
    org_id: str
    name: str
    system_prompt: str
    voice_id: str | None
    language: str
    simple_mode: bool
    graph_config: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
