"""SessionEvent model — one row per execution event within a session turn.

event_type values:
  node       — a LangGraph node executed (on_chain_start/end)
  llm        — a chat model call (on_chat_model_start/end)
  tool       — a tool invocation (on_tool_start/end)
  error      — unhandled exception during graph execution
  interrupt  — graph paused for user input
"""
from sqlalchemy import Column, DateTime, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from vaaniq.server.core.database import Base


class SessionEvent(Base):
    __tablename__ = "session_events"

    id          = Column(String,                  primary_key=True)
    session_id  = Column(String,                  nullable=False)          # FK enforced in migration
    turn        = Column(SmallInteger,            nullable=False)          # 0-based per-session counter
    seq         = Column(SmallInteger,            nullable=False)          # ordering within a turn
    event_type  = Column(String,                  nullable=False)          # node | llm | tool | error | interrupt
    name        = Column(String,                  nullable=False, default="")  # node_id / model name / tool name
    started_at  = Column(DateTime(timezone=True), nullable=False)
    ended_at    = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer,                 nullable=True)
    status      = Column(String,                  nullable=False, default="success")  # success | error | interrupted
    data        = Column(JSONB,                   nullable=False, default=dict)
    error       = Column(Text,                    nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
