"""
StartNode — one-time entry node executed when a session begins.

Config:
    system_message  (str)  agent persona / global instructions injected into
                           every llm_response node in this graph
    greeting        (str)  static message sent to the user immediately when
                           the session opens, before any user input (optional)
"""
from datetime import datetime, timezone

from naaviq.core.state import Message
from naaviq.graph.nodes.base import BaseNode
from naaviq.graph.state import GraphSessionState


class StartNode(BaseNode):
    async def __call__(self, state: GraphSessionState) -> dict:
        updates: dict = {"current_node": "start"}

        system_message: str = self.config.get("system_message", "")
        greeting: str = self.config.get("greeting", "")

        if system_message:
            updates["system_message"] = system_message

        if greeting:
            now = datetime.now(timezone.utc).isoformat()
            agent_msg: Message = {
                "role": "agent",
                "content": greeting,
                "timestamp": now,
                "node_id": "start",
            }
            updates["messages"] = [agent_msg]

        return updates
