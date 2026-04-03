"""
LLMResponseNode — the main agent response node.

When config.tools is non-empty, runs a ReAct loop:
  LLM → tool_call? → execute → ToolMessage → LLM → ... → final text

When config.tools is empty, makes a single LLM call (simple conversational mode).

Context window guard: trim_messages is applied before every LLM call so the
conversation never exceeds _MAX_CONTEXT_TOKENS. This is Tier 1 of our context
window strategy — silent, zero-latency, fires only when approaching the limit.
See ARCHITECTURE.md for the full 3-tier plan.

Config:
    instructions  (str)    system prompt / agent persona
    rag_enabled   (bool)   inject state["rag_context"] into system prompt
    tools         (list)   tool names from TOOL_REGISTRY to make available
    voice_id      (str)    passed through to TTS layer (not used here)
    provider      (str)    optional — see llm.py
    model         (str)    optional — see llm.py
    temperature   (float)  optional — see llm.py
"""
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    trim_messages,
)
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

from vaaniq.core.state import Message, ToolCall
from vaaniq.graph.nodes.base import BaseNode
from vaaniq.graph.nodes.llm import get_llm
from vaaniq.graph.state import GraphSessionState

_MAX_REACT_ITERATIONS = 10
# Rough token budget — trim_messages fires only when history is very long.
# 4 chars ≈ 1 token; 50 000 tokens ≈ 200 000 chars.
_MAX_CONTEXT_TOKENS = 50_000

_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _count_tokens(messages: list) -> int:
    """Rough token estimate: sum of content lengths ÷ 4."""
    return sum(len(str(getattr(m, "content", ""))) for m in messages) // 4


def _to_lc_messages(state: GraphSessionState) -> list:
    result = []
    for msg in state.get("messages", []):
        if msg["role"] == "user":
            result.append(HumanMessage(content=msg["content"]))
        else:
            result.append(AIMessage(content=msg["content"]))
    return result


# ── Tool wrapping ─────────────────────────────────────────────────────────────


def _make_args_schema(tool_name: str, input_schema: dict):
    """Build a Pydantic model from a JSON Schema dict for use with StructuredTool."""
    props = input_schema.get("properties", {})
    if not props:
        return None
    required_set = set(input_schema.get("required", []))
    fields: dict[str, Any] = {}
    for fname, finfo in props.items():
        py_type = _JSON_TYPE_MAP.get(finfo.get("type", "string"), str)
        desc = finfo.get("description", "")
        if fname in required_set:
            fields[fname] = (py_type, Field(description=desc))
        else:
            default = finfo.get("default", None)
            fields[fname] = (Optional[py_type], Field(default=default, description=desc))
    return create_model(f"{tool_name}_input", **fields)


def _wrap_as_lc_tool(vaaniq_tool: Any, org_keys: dict) -> StructuredTool:
    """Convert a vaaniq BaseTool into a LangChain StructuredTool."""
    _tool = vaaniq_tool
    _keys = org_keys

    async def _run(**kwargs: Any) -> str:
        result = await _tool.run(kwargs, _keys)
        return str(result)

    build_kwargs: dict[str, Any] = dict(
        coroutine=_run,
        name=_tool.name,
        description=_tool.description,
    )
    schema = _make_args_schema(_tool.name, getattr(_tool, "input_schema", {}))
    if schema is not None:
        build_kwargs["args_schema"] = schema
    return StructuredTool.from_function(**build_kwargs)


# ── ReAct loop ────────────────────────────────────────────────────────────────


async def _react_loop(
    llm_with_tools: Any,
    messages: list,
    lc_tools: list[StructuredTool],
) -> tuple[str, list[ToolCall]]:
    """Drive the LLM until it stops issuing tool calls or hits the iteration cap.

    Returns (final_text_content, new_tool_call_records).
    """
    tool_map = {t.name: t for t in lc_tools}
    new_tool_calls: list[ToolCall] = []
    response = None

    for _ in range(_MAX_REACT_ITERATIONS):
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        if not getattr(response, "tool_calls", None):
            break

        for tc in response.tool_calls:
            name: str = tc["name"]
            args: dict = tc["args"]
            call_id: str = tc["id"]
            called_at = datetime.now(timezone.utc).isoformat()

            if name in tool_map:
                try:
                    result = await tool_map[name].ainvoke(args)
                    messages.append(ToolMessage(content=str(result), tool_call_id=call_id))
                    new_tool_calls.append({  # type: ignore[misc]
                        "tool_name": name,
                        "input": args,
                        "output": result,
                        "called_at": called_at,
                        "success": True,
                    })
                except Exception as exc:
                    err_msg = f"Tool '{name}' raised an error: {exc}"
                    messages.append(ToolMessage(content=err_msg, tool_call_id=call_id))
                    new_tool_calls.append({  # type: ignore[misc]
                        "tool_name": name,
                        "input": args,
                        "output": {"error": str(exc)},
                        "called_at": called_at,
                        "success": False,
                    })
            else:
                messages.append(
                    ToolMessage(content=f"Tool '{name}' is not available.", tool_call_id=call_id)
                )

    content: str = getattr(response, "content", "") or "I encountered an issue. Please try again."
    return content, new_tool_calls


# ── Node ──────────────────────────────────────────────────────────────────────


class LLMResponseNode(BaseNode):
    async def __call__(self, state: GraphSessionState) -> dict:
        from vaaniq.tools.registry import TOOL_REGISTRY  # deferred to avoid circular import

        instructions: str = self.config.get("instructions", "You are a helpful assistant.")
        rag_enabled: bool = self.config.get("rag_enabled", False)
        tool_names: list[str] = self.config.get("tools", [])

        system_parts = [instructions]
        if rag_enabled and state.get("rag_context"):
            system_parts.append(f"\n\nRelevant context from knowledge base:\n{state['rag_context']}")
        system = "\n".join(system_parts)

        llm = get_llm(self.config, self.org_keys)

        # Build LC history and apply context window guard
        lc_history = _to_lc_messages(state)
        lc_history = trim_messages(
            lc_history,
            max_tokens=_MAX_CONTEXT_TOKENS,
            token_counter=_count_tokens,
            strategy="last",
            allow_partial=False,
        )
        base_messages = [SystemMessage(content=system)] + lc_history

        if not tool_names:
            response = await llm.ainvoke(base_messages)
            final_content: str = response.content
            new_tool_calls: list = []
        else:
            lc_tools = [
                _wrap_as_lc_tool(TOOL_REGISTRY[name], self.org_keys)
                for name in tool_names
                if name in TOOL_REGISTRY
            ]
            llm_with_tools = llm.bind_tools(lc_tools)
            final_content, new_tool_calls = await _react_loop(llm_with_tools, list(base_messages), lc_tools)

        now = datetime.now(timezone.utc).isoformat()
        agent_msg: Message = {
            "role": "agent",
            "content": final_content,
            "timestamp": now,
            "node_id": "llm_response",
        }
        result: dict = {
            "messages": [agent_msg],
            "current_node": "llm_response",
        }
        if new_tool_calls:
            result["tool_calls"] = new_tool_calls
        return result
