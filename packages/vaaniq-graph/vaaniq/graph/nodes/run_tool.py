"""
RunToolNode — call a specific pre-built tool directly without LLM decision.

Config:
    tool              (str)   tool name from TOOL_REGISTRY
    input             (dict)  input params — supports {{template}} syntax
    save_response_to  (str)   state key to store the tool result (optional)
"""
import structlog
from datetime import datetime, timezone

from vaaniq.graph.nodes.base import BaseNode, PROTECTED_STATE_KEYS
from vaaniq.graph.resolver import TemplateResolver
from vaaniq.core.state import SessionState

log = structlog.get_logger()


class RunToolNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        from vaaniq.tools.registry import TOOL_REGISTRY

        tool_name: str = self.config.get("tool", "")
        save_key: str | None = self.config.get("save_response_to")
        now = datetime.now(timezone.utc).isoformat()

        # Validate save_response_to before doing any work
        if save_key and save_key in PROTECTED_STATE_KEYS:
            error_msg = f"save_response_to: '{save_key}' is a protected state key and cannot be overwritten."
            log.error("run_tool_protected_key", key=save_key, tool=tool_name, session_id=state.get("session_id"))
            return {"error": error_msg, "current_node": "run_tool"}

        tool = TOOL_REGISTRY.get(tool_name)
        if not tool:
            error_msg = f"Tool '{tool_name}' not found in registry."
            log.warning("run_tool_not_found", tool=tool_name, session_id=state.get("session_id"))
            return {"error": error_msg, "current_node": "run_tool"}

        resolved_input = TemplateResolver.resolve(
            self.config.get("input", {}), state, self.org_keys
        )

        # Normalize + type-coerce inputs. Tools override normalize_input() for
        # semantic validation (e.g. end_time > start_time for calendar events).
        try:
            resolved_input = tool.normalize_input(resolved_input)
        except ValueError as exc:
            error_msg = f"Input validation failed for '{tool_name}': {exc}"
            log.error("run_tool_validation_error", tool=tool_name, error=str(exc), session_id=state.get("session_id"))
            return {
                "error": error_msg,
                "current_node": "run_tool",
                "run_tool_debug": {"tool_name": tool_name, "input": resolved_input, "output": str(exc)},
            }

        # Validate required inputs before calling the tool.
        # TemplateResolver returns None for missing {{collected.field}} references.
        # Catching this here gives a clear error ("missing required input: end_time")
        # instead of a cryptic KeyError inside the tool implementation.
        input_schema: dict = getattr(tool, "input_schema", {}) or {}
        required_fields: list[str] = input_schema.get("required", [])
        missing = [f for f in required_fields if resolved_input.get(f) is None]
        if missing:
            error_msg = (
                f"Tool '{tool_name}' is missing required input(s): {', '.join(missing)}. "
                f"Make sure your collect_data node collects these fields, or set them via set_variable."
            )
            log.error("run_tool_missing_inputs", tool=tool_name, missing=missing, session_id=state.get("session_id"))
            return {
                "error": error_msg,
                "current_node": "run_tool",
                "run_tool_debug": {"tool_name": tool_name, "input": resolved_input, "output": None},
            }

        log.info("run_tool_start", tool=tool_name, session_id=state.get("session_id"))

        try:
            result = await tool.run(resolved_input, self.org_keys)
        except Exception as exc:
            error_msg = f"Tool '{tool_name}' failed: {exc}"
            log.error("run_tool_error", tool=tool_name, error=str(exc), session_id=state.get("session_id"))
            return {
                "error": error_msg,
                "current_node": "run_tool",
                "run_tool_debug": {"tool_name": tool_name, "input": resolved_input, "output": str(exc)},
            }

        log.info("run_tool_done", tool=tool_name, session_id=state.get("session_id"))

        tool_call = {
            "tool_name": tool_name,
            "input": resolved_input,
            "output": result,
            "called_at": now,
            "success": True,
        }

        updates: dict = {
            "tool_calls": [tool_call],
            "current_node": "run_tool",
        }

        if save_key:
            updates[save_key] = result

        return updates
