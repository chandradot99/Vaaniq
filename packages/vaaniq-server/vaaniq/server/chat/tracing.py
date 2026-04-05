"""Execution tracing for chat sessions.

TurnEventCollector — collects LangGraph execution events during a single
agent turn and produces SessionEvent rows ready for bulk DB insert.

Supports two integration modes:
  1. Streaming  — call collector.ingest(event) inside an astream_events loop
  2. Non-streaming — use collector.as_callback_handler() as a LangChain callback

Both modes produce identical output via the same internal _ingest_parsed() path.

SessionEventRepository — persistence layer for session_events table.
"""
import json
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_core.callbacks.base import BaseCallbackHandler
from sqlalchemy.ext.asyncio import AsyncSession

from vaaniq.server.models.session_event import SessionEvent

log = structlog.get_logger()

# LangGraph-internal chain names we never want in the timeline
_SKIP_NAMES = {"LangGraph", "__start__", ""}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ms(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() * 1000))


def _truncate(obj: Any, max_bytes: int = 65_536) -> Any:
    """Truncate large objects to avoid unbounded JSONB growth."""
    try:
        s = json.dumps(obj)
        if len(s) <= max_bytes:
            return obj
        return s[:max_bytes] + "…[truncated]"
    except Exception:
        return str(obj)[:max_bytes]


# ── TurnEventCollector ────────────────────────────────────────────────────────


class TurnEventCollector:
    """Collect execution events for a single agent turn.

    Usage (streaming path):
        collector = TurnEventCollector(session_id, turn, graph_config)
        async for event in graph.astream_events(..., version="v2"):
            collector.ingest(event)
            # ... yield SSE as usual
        collector.add_interrupt(interrupt_info)   # if applicable
        events = collector.finalize()
        await SessionEventRepository(db).bulk_insert(events)

    Usage (ainvoke path):
        collector = TurnEventCollector(session_id, turn, graph_config)
        config["callbacks"].append(collector.as_callback_handler())
        result = await graph.ainvoke(state, config=config)
        events = collector.finalize()
        await SessionEventRepository(db).bulk_insert(events)
    """

    def __init__(self, session_id: str, turn: int, graph_config: dict | None = None) -> None:
        self.session_id = session_id
        self.turn = turn
        # node_id → node_type mapping built from graph config for data enrichment
        self._node_type_map: dict[str, str] = {}
        if graph_config:
            for node in graph_config.get("nodes", []):
                self._node_type_map[node["id"]] = node.get("type", "")

        # run_id → {started_at, name, event_type, data} for in-flight events
        self._pending: dict[str, dict] = {}
        # completed event dicts in emission order
        self._finalized: list[dict] = []
        self._seq = 0

    # ── Public interface ──────────────────────────────────────────────────────

    def ingest(self, event: dict) -> None:
        """Process one astream_events v2 event dict."""
        kind: str = event.get("event", "")
        name: str = event.get("name", "")
        run_id: str = event.get("run_id", "")
        metadata: dict = event.get("metadata", {})

        if kind == "on_chain_start":
            if name in _SKIP_NAMES:
                return
            # Skip internal LangGraph nodes that are not in the user's graph config
            if self._node_type_map and name not in self._node_type_map:
                return
            self._pending[run_id] = {
                "event_type": "node",
                "name": name,
                "started_at": _now(),
                "data": {
                    "node_type": self._node_type_map.get(name, ""),
                },
            }

        elif kind == "on_chain_end":
            if name in _SKIP_NAMES:
                return
            pending = self._pending.pop(run_id, None)
            if pending:
                ended = _now()
                # Check if the node signalled a failure via its return dict.
                # Nodes that error return {"error": "..."} instead of raising,
                # so LangGraph still fires on_chain_end — we inspect the output
                # here to mark the node as errored in the timeline.
                output = event.get("data", {}).get("output")
                node_error = output.get("error") if isinstance(output, dict) else None
                data = pending["data"]

                # For run_tool nodes: embed the resolved input + output so the
                # frontend debug panel can show exactly what was sent and received.
                if isinstance(output, dict) and data.get("node_type") == "run_tool":
                    tool_calls = output.get("tool_calls") or []
                    if tool_calls:
                        # Success path — tool_calls list is populated
                        tc = tool_calls[0]
                        data = {
                            **data,
                            "tool_name": tc.get("tool_name", ""),
                            "tool_input": _truncate(tc.get("input", {})),
                            "tool_output": _truncate(tc.get("output")),
                            "tool_success": True,
                        }
                    else:
                        # Error path — run_tool_debug carries the resolved input + error response
                        debug = output.get("run_tool_debug") or {}
                        data = {
                            **data,
                            "tool_name": debug.get("tool_name", ""),
                            "tool_input": _truncate(debug.get("input", {})),
                            "tool_output": _truncate(debug.get("output")),
                            "tool_success": False,
                        }

                self._emit(
                    event_type="node",
                    name=pending["name"],
                    started_at=pending["started_at"],
                    ended_at=ended,
                    status="error" if node_error else "success",
                    data=data,
                    error=node_error,
                )

        elif kind == "on_chat_model_start":
            parent_node = metadata.get("langgraph_node", "")
            self._pending[run_id] = {
                "event_type": "llm",
                "name": name,
                "started_at": _now(),
                "data": {
                    "parent_node": parent_node,
                    "model": "",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }

        elif kind == "on_chat_model_end":
            pending = self._pending.pop(run_id, None)
            if pending:
                ended = _now()
                output = event.get("data", {}).get("output")
                usage = getattr(output, "usage_metadata", None) or {}
                resp_meta = getattr(output, "response_metadata", None) or {}
                model = resp_meta.get("model_name") or resp_meta.get("model") or pending["name"]
                data = {
                    **pending["data"],
                    "model": model,
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }
                self._emit(
                    event_type="llm",
                    name=model,
                    started_at=pending["started_at"],
                    ended_at=ended,
                    status="success",
                    data=data,
                )

        elif kind == "on_tool_start":
            parent_node = metadata.get("langgraph_node", "")
            tool_input = event.get("data", {}).get("input", {})
            self._pending[run_id] = {
                "event_type": "tool",
                "name": name,
                "started_at": _now(),
                "data": {
                    "tool_name": name,
                    "input": _truncate(tool_input),
                    "parent_node": parent_node,
                },
            }

        elif kind == "on_tool_end":
            pending = self._pending.pop(run_id, None)
            if pending:
                ended = _now()
                output = event.get("data", {}).get("output")
                output_val = getattr(output, "content", output) if output is not None else None
                data = {
                    **pending["data"],
                    "output": _truncate(output_val),
                    "success": True,
                }
                self._emit(
                    event_type="tool",
                    name=pending["name"],
                    started_at=pending["started_at"],
                    ended_at=ended,
                    status="success",
                    data=data,
                )

    def add_interrupt(self, interrupt_info: dict) -> None:
        """Record a graph interrupt (collect_question, human_review, user_input)."""
        self._emit(
            event_type="interrupt",
            name=interrupt_info.get("node", ""),
            started_at=_now(),
            ended_at=None,
            status="interrupted",
            data=interrupt_info,
        )

    def add_error(self, exc: Exception, current_node: str = "") -> None:
        """Record an unhandled exception."""
        self._emit(
            event_type="error",
            name=current_node,
            started_at=_now(),
            ended_at=None,
            status="error",
            data={
                "node": current_node,
                "exception_type": type(exc).__name__,
            },
            error=traceback.format_exc(),
        )

    def finalize(self) -> list[SessionEvent]:
        """Return SessionEvent ORM instances ready for db.add_all()."""
        # Any events still pending (e.g. error mid-stream) are discarded —
        # they have no end time and are not useful in the timeline.
        rows = []
        for i, ev in enumerate(self._finalized):
            rows.append(SessionEvent(
                id=str(uuid.uuid4()),
                session_id=self.session_id,
                turn=self.turn,
                seq=i,
                event_type=ev["event_type"],
                name=ev["name"],
                started_at=ev["started_at"],
                ended_at=ev.get("ended_at"),
                duration_ms=ev.get("duration_ms"),
                status=ev["status"],
                data=ev["data"],
                error=ev.get("error"),
            ))
        return rows

    def as_callback_handler(self) -> BaseCallbackHandler:
        """Return a LangChain callback handler that feeds into this collector.

        Used by the non-streaming ainvoke path so both paths share the same
        _ingest_parsed() logic.
        """
        return _CollectorCallbackHandler(self)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _emit(
        self,
        event_type: str,
        name: str,
        started_at: datetime,
        ended_at: datetime | None,
        status: str,
        data: dict,
        error: str | None = None,
    ) -> None:
        duration_ms = _ms(started_at, ended_at) if ended_at else None
        self._finalized.append({
            "event_type": event_type,
            "name": name,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
            "status": status,
            "data": data,
            "error": error,
        })


# ── Callback handler adapter ──────────────────────────────────────────────────


class _CollectorCallbackHandler(BaseCallbackHandler):
    """Thin LangChain callback adapter that converts ainvoke callbacks into
    astream_events-style dicts and passes them to TurnEventCollector.ingest().

    This keeps all parsing logic in one place (TurnEventCollector) regardless
    of whether the graph was invoked via ainvoke or astream_events.
    """

    def __init__(self, collector: TurnEventCollector) -> None:
        super().__init__()
        self._c = collector

    def on_chain_start(self, serialized: dict, inputs: dict, *, run_id: uuid.UUID, parent_run_id: uuid.UUID | None = None, name: str | None = None, **kwargs: Any) -> None:  # noqa: ARG002
        node_name = name or (serialized.get("id", [""])[-1] if serialized.get("id") else "")
        self._c.ingest({
            "event": "on_chain_start",
            "name": node_name,
            "run_id": str(run_id),
            "metadata": {"langgraph_node": node_name},
        })

    def on_chain_end(self, outputs: dict, *, run_id: uuid.UUID, parent_run_id: uuid.UUID | None = None, **kwargs: Any) -> None:  # noqa: ARG002
        run_id_str = str(run_id)
        pending = self._c._pending.get(run_id_str, {})
        self._c.ingest({
            "event": "on_chain_end",
            "name": pending.get("name", ""),
            "run_id": run_id_str,
            "metadata": {},
            "data": {"output": outputs},  # pass output so ingest can detect node errors
        })

    def on_llm_start(self, serialized: dict, prompts: list, *, run_id: uuid.UUID, parent_run_id: uuid.UUID | None = None, **kwargs: Any) -> None:  # noqa: ARG002
        model_name = serialized.get("kwargs", {}).get("model_name") or serialized.get("id", ["llm"])[-1]
        parent_node = kwargs.get("metadata", {}).get("langgraph_node", "")
        self._c.ingest({
            "event": "on_chat_model_start",
            "name": model_name,
            "run_id": str(run_id),
            "metadata": {"langgraph_node": parent_node},
        })

    def on_llm_end(self, response: Any, *, run_id: uuid.UUID, parent_run_id: uuid.UUID | None = None, **kwargs: Any) -> None:  # noqa: ARG002
        run_id_str = str(run_id)
        pending = self._c._pending.get(run_id_str, {})
        # Extract usage from LLMResult
        usage: dict = {}
        if hasattr(response, "llm_output") and response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
            usage = {
                "input_tokens": token_usage.get("prompt_tokens", 0),
                "output_tokens": token_usage.get("completion_tokens", 0),
                "total_tokens": token_usage.get("total_tokens", 0),
            }

        class _FakeOutput:
            usage_metadata = usage
            response_metadata: dict = {}

        self._c.ingest({
            "event": "on_chat_model_end",
            "name": pending.get("name", ""),
            "run_id": run_id_str,
            "metadata": {},
            "data": {"output": _FakeOutput()},
        })

    def on_tool_start(self, serialized: dict, input_str: str, *, run_id: uuid.UUID, parent_run_id: uuid.UUID | None = None, **kwargs: Any) -> None:  # noqa: ARG002
        tool_name = serialized.get("name") or serialized.get("id", ["tool"])[-1]
        parent_node = kwargs.get("metadata", {}).get("langgraph_node", "")
        try:
            tool_input = json.loads(input_str)
        except Exception:
            tool_input = {"input": input_str}
        self._c.ingest({
            "event": "on_tool_start",
            "name": tool_name,
            "run_id": str(run_id),
            "metadata": {"langgraph_node": parent_node},
            "data": {"input": tool_input},
        })

    def on_tool_end(self, output: Any, *, run_id: uuid.UUID, parent_run_id: uuid.UUID | None = None, **kwargs: Any) -> None:  # noqa: ARG002
        run_id_str = str(run_id)
        pending = self._c._pending.get(run_id_str, {})
        self._c.ingest({
            "event": "on_tool_end",
            "name": pending.get("name", ""),
            "run_id": run_id_str,
            "metadata": {},
            "data": {"output": output},
        })


# ── Repository ────────────────────────────────────────────────────────────────


class SessionEventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def bulk_insert(self, events: list[SessionEvent]) -> None:
        """Insert all events for a turn in a single statement."""
        if not events:
            return
        for event in events:
            self.db.add(event)

    async def list_by_session(self, session_id: str) -> list[SessionEvent]:
        from sqlalchemy import select
        result = await self.db.execute(
            select(SessionEvent)
            .where(SessionEvent.session_id == session_id)
            .order_by(SessionEvent.turn, SessionEvent.seq)
        )
        return list(result.scalars().all())
