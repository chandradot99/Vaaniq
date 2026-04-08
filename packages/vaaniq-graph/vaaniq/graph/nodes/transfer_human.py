"""
TransferHumanNode — hand the session off to a real agent.

Sets transfer_initiated and transfer_to so the channel handler
(Pipecat / SSE) can execute the actual transfer.

Config:
    transfer_number   (str)  phone number or agent queue ID to transfer to
    whisper_template  (str)  optional message whispered to the receiving agent
                             (context about the conversation — NOT shown to the user)
                             supports {{template}} syntax
    hold_message      (str)  optional message shown to the user while transferring
                             defaults to "Transferring you to a human agent. Please hold."
"""
from datetime import datetime, timezone

from vaaniq.core.state import Message, SessionState
from vaaniq.graph.nodes.base import BaseNode
from vaaniq.graph.resolver import TemplateResolver


class TransferHumanNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        transfer_to: str = self.config.get("transfer_number", "")
        whisper_template: str = self.config.get("whisper_template", "")
        hold_message: str = self.config.get(
            "hold_message",
            "Transferring you to a human agent. Please hold.",
        )

        # Resolve whisper template against state — this is context for the
        # receiving agent, e.g. "Customer asking about invoice #{{collected.invoice_id}}"
        # It is stored in state["whisper_message"] for the channel handler to use.
        # It is intentionally NOT added to state["messages"] (not shown to the user).
        whisper: str = ""
        if whisper_template:
            whisper = TemplateResolver.resolve_value(whisper_template, state, self.org_keys)

        now = datetime.now(timezone.utc).isoformat()
        user_msg: Message = {
            "role": "agent",
            "content": hold_message,
            "timestamp": now,
            "node_id": "transfer_human",
        }

        return {
            "messages": [user_msg],
            "transfer_initiated": True,
            "transfer_to": transfer_to,
            "whisper_message": whisper or None,
        }
