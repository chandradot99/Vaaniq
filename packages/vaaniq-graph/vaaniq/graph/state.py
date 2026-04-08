"""
GraphSessionState — LangGraph-aware state with reducers.

vaaniq-core's SessionState is a plain TypedDict with no external deps.
This module extends it with LangGraph reducers so the graph engine
can merge partial updates correctly.

Why separate from vaaniq-core:
  vaaniq-core must stay dependency-free (it's the contract used by all
  packages). LangGraph reducers are a graph-execution concern only.

Reducers:
  messages    operator.add   → nodes return [new_msg], list is appended
  tool_calls  operator.add   → nodes return [new_call], list is appended
  collected   dict_merge     → nodes return {"name": "Rahul"}, dict is merged
  action_items operator.add  → nodes return [new_item], list is appended
  post_actions_completed operator.add

  current_node  last_value     → lambda _a, b: b — last write wins
  route         last_value     → lambda _a, b: b — last write wins
  error         last_value     → lambda _a, b: b — last write wins

All other fields have no reducer — nodes overwrite them directly.
"""
import operator
from typing import Annotated, Any, Literal, Optional

from typing_extensions import TypedDict
from vaaniq.core.state import Message, ToolCall


def _dict_merge(a: dict, b: dict) -> dict:
    """Merge two dicts — b wins on key conflicts."""
    return {**a, **b}


class GraphSessionState(TypedDict):
    # ── Identity ──────────────────────────────────────────────────────────
    session_id: str
    agent_id: str
    org_id: str
    channel: Literal["voice", "chat", "whatsapp", "sms", "telegram"]
    user_id: str

    # ── Conversation ──────────────────────────────────────────────────────
    # Reducer: append — nodes return [new_msg], never the full list
    messages: Annotated[list[Message], operator.add]

    # ── Graph state ───────────────────────────────────────────────────────
    # last_value reducer: if multiple nodes update these scalars in the same
    # superstep (fan-out / resumed interrupt), take the last write instead of
    # raising INVALID_CONCURRENT_GRAPH_UPDATE.
    current_node: Annotated[str, lambda _a, b: b]
    route: Annotated[Optional[str], lambda _a, b: b]

    # ── Collected data ────────────────────────────────────────────────────
    # Reducer: merge — nodes return {"field": value}, dict is merged
    collected: Annotated[dict[str, Any], _dict_merge]

    # ── Context ───────────────────────────────────────────────────────────
    system_message: str   # set by start node; injected into all llm_response nodes
    rag_context: str
    crm_record: Optional[dict[str, Any]]

    # ── Tool calls ────────────────────────────────────────────────────────
    # Reducer: append — nodes return [new_call], never the full list
    tool_calls: Annotated[list[ToolCall], operator.add]

    # ── Transfer ──────────────────────────────────────────────────────────
    transfer_to: Optional[str]
    whisper_message: Optional[str]
    transfer_initiated: bool

    # ── Session lifecycle ─────────────────────────────────────────────────
    start_time: str
    end_time: Optional[str]
    duration_seconds: Optional[int]
    session_ended: bool

    # ── Post-session ──────────────────────────────────────────────────────
    summary: Optional[str]
    sentiment: Optional[str]
    action_items: Annotated[list[str], operator.add]
    post_actions_completed: Annotated[list[str], operator.add]

    # ── Error handling ────────────────────────────────────────────────────
    error: Annotated[Optional[str], lambda _a, b: b]
