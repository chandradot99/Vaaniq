"""
RunToolNode — call a specific pre-built tool directly without LLM decision.

Config:
    tool              (str)   tool name from TOOL_REGISTRY
    input             (dict)  input params — supports {{template}} syntax
    save_response_to  (str)   state key to store the tool result (optional)
"""
import structlog
from datetime import datetime, timezone

from vaaniq.graph.nodes.base import BaseNode
from vaaniq.graph.resolver import TemplateResolver
from vaaniq.core.state import SessionState

log = structlog.get_logger()


class RunToolNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        from vaaniq.tools.registry import TOOL_REGISTRY

        tool_name: str = self.config.get("tool", "")
        tool = TOOL_REGISTRY.get(tool_name)

        if not tool:
            log.warning("run_tool_not_found", tool=tool_name)
            return {"error": f"Tool '{tool_name}' not found in registry"}

        resolved_input = TemplateResolver.resolve(
            self.config.get("input", {}), state, self.org_keys
        )

        log.info("run_tool_start", tool=tool_name, session_id=state.get("session_id"))

        try:
            result = await tool.run(resolved_input, self.org_keys)
        except Exception as exc:
            log.error("run_tool_error", tool=tool_name, error=str(exc))
            return {"error": f"Tool '{tool_name}' failed: {exc}"}

        log.info("run_tool_done", tool=tool_name)

        tool_call = {
            "tool_name": tool_name,
            "input": resolved_input,
            "output": result,
            "called_at": datetime.now(timezone.utc).isoformat(),
            "success": True,
        }

        updates: dict = {
            "tool_calls": [tool_call],
            "current_node": state.get("current_node", ""),
        }

        save_key = self.config.get("save_response_to")
        if save_key:
            updates[save_key] = result

        return updates
