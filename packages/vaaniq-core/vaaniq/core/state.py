from typing import Any, Literal, Optional
from typing_extensions import TypedDict


class Message(TypedDict):
    role: str
    content: str
    timestamp: str
    node_id: str


class ToolCall(TypedDict):
    tool_name: str
    input: dict[str, Any]
    output: Any
    called_at: str
    success: bool


class SessionState(TypedDict):
    session_id: str
    agent_id: str
    org_id: str
    channel: Literal["voice", "chat", "whatsapp", "sms", "telegram"]
    user_id: str
    messages: list[Message]
    current_node: str
    collected: dict[str, Any]
    rag_context: str
    crm_record: Optional[dict[str, Any]]
    tool_calls: list[ToolCall]
    route: Optional[str]
    transfer_to: Optional[str]
    start_time: str
    end_time: Optional[str]
    duration_seconds: Optional[int]
    summary: Optional[str]
    sentiment: Optional[str]
    action_items: list[str]
    post_actions_completed: list[str]
    session_ended: bool
    transfer_initiated: bool
    error: Optional[str]
