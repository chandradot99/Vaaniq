"""
RunToolNode — call a specific pre-built tool directly without LLM decision.

Tool wiring will be added when vaaniq-tools is implemented.
For now this node is a stub that returns an error if invoked.

Config:
    tool              (str)   tool name from TOOL_REGISTRY (future)
    input             (dict)  input params — supports {{template}} syntax
    save_response_to  (str)   state key to store the tool result (optional)
"""
from vaaniq.graph.nodes.base import BaseNode
from vaaniq.core.state import SessionState


class RunToolNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        tool_name: str = self.config.get("tool", "unknown")
        return {"error": f"Tool {tool_name!r} not available — vaaniq-tools not yet implemented"}
