from datetime import datetime
from typing import Any, Optional
from vaaniq.server.core.schemas import CustomModel


class ChatMessage(CustomModel):
    role: str       # "agent" | "user"
    content: str


class StartChatResponse(CustomModel):
    session_id: str
    messages: list[ChatMessage]
    session_ended: bool = False


class SendMessageRequest(CustomModel):
    session_id: str
    message: str


class SendMessageResponse(CustomModel):
    messages: list[ChatMessage]   # new messages since last turn (agent only)
    session_ended: bool = False


# ── Sessions list / detail ────────────────────────────────────────────────────

class SessionSummary(CustomModel):
    id: str
    agent_id: str
    status: str                         # active | ended
    channel: str
    message_count: int
    tool_call_count: int
    duration_seconds: Optional[int]
    sentiment: Optional[str]
    created_at: datetime
    ended_at: Optional[datetime]


class ToolCallDetail(CustomModel):
    tool_name: str
    input: dict[str, Any]
    output: Any
    called_at: str
    success: bool


class TranscriptMessage(CustomModel):
    role: str
    content: str
    timestamp: Optional[str] = None
    node_id: Optional[str] = None


class SessionDetail(CustomModel):
    id: str
    agent_id: str
    status: str
    channel: str
    duration_seconds: Optional[int]
    sentiment: Optional[str]
    summary: Optional[str]
    meta: dict[str, Any]
    transcript: list[TranscriptMessage]
    tool_calls: list[ToolCallDetail]
    created_at: datetime
    ended_at: Optional[datetime]


class SessionListResponse(CustomModel):
    sessions: list[SessionSummary]
    total: int


# ── Execution timeline ────────────────────────────────────────────────────────

class SessionEventSchema(CustomModel):
    id: str
    turn: int
    seq: int
    event_type: str          # node | llm | tool | error | interrupt
    name: str
    started_at: datetime
    ended_at: Optional[datetime]
    duration_ms: Optional[int]
    status: str              # success | error | interrupted
    data: dict[str, Any]
    error: Optional[str]


class SessionTimeline(CustomModel):
    session_id: str
    events: list[SessionEventSchema]
    total_turns: int
    total_llm_tokens: int
    total_duration_ms: int
