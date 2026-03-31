from typing import Any, Optional
from pydantic import BaseModel


class AgentConfig(BaseModel):
    agent_id: str
    org_id: str
    name: str
    system_prompt: str
    voice_id: Optional[str] = None
    language: str = "en"
    graph_config: dict[str, Any] = {}
    simple_mode: bool = False
