"""
EndSessionNode — end the session gracefully.

Appends a farewell message and marks the session as ended.

Config:
    farewell_message (str)  message to send before closing
"""
from datetime import datetime, timezone

from vaaniq.graph.nodes.base import BaseNode
from vaaniq.core.state import SessionState, Message


class EndSessionNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        farewell = self.config.get("farewell_message", "Goodbye!")

        now = datetime.now(timezone.utc).isoformat()
        farewell_msg: Message = {
            "role": "agent",
            "content": farewell,
            "timestamp": now,
            "node_id": "end_session",
        }

        start = state.get("start_time")
        duration = None
        if start:
            try:
                delta = datetime.fromisoformat(now) - datetime.fromisoformat(start)
                duration = int(delta.total_seconds())
            except ValueError:
                pass

        return {
            "messages": [farewell_msg],   # reducer appends
            "session_ended": True,
            "end_time": now,
            "duration_seconds": duration,
        }
