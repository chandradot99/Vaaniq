from typing import Any, Optional
from vaaniq.server.core.schemas import CustomModel


class AgentCreate(CustomModel):
    name: str
    system_prompt: str = ""
    voice_id: Optional[str] = None
    language: str = "en"
    simple_mode: bool = False


class AgentUpdate(CustomModel):
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    voice_id: Optional[str] = None
    language: Optional[str] = None
    simple_mode: Optional[bool] = None


class AgentResponse(CustomModel):
    id: str
    org_id: str
    name: str
    system_prompt: str
    voice_id: Optional[str]
    language: str
    graph_config: dict[str, Any]
    simple_mode: bool
