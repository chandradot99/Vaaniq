"""
InboundMessageNode — wait for a user message and add it to conversation.

Used in chat and WhatsApp flows to pause the graph between agent turns.
For voice (Pipecat/LiveKit) this node is not needed — the audio pipeline
handles turn-taking externally.

Place this node immediately after an llm_response node so the graph
pauses and waits for the user to reply before routing to a condition
or the next step.

Config: (none required)
"""
from datetime import datetime, timezone

from langgraph.types import interrupt

from vaaniq.graph.nodes.base import BaseNode
from vaaniq.core.state import SessionState, Message


class InboundMessageNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        # Pause here — chat service resumes with the user's message text
        user_text: str = interrupt({"type": "user_input", "waiting": True})

        now = datetime.now(timezone.utc).isoformat()
        user_msg: Message = {
            "role": "user",
            "content": user_text,
            "timestamp": now,
            "node_id": "inbound_message",
        }

        return {
            "messages": [user_msg],
            "current_node": "inbound_message",
        }
