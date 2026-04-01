"""
TransferHumanNode — hand the session off to a real agent.

Sets transfer_initiated and transfer_to so the channel handler
(Pipecat / SSE) can execute the actual transfer.

Config:
    transfer_number   (str)  phone number or agent queue ID to transfer to
    whisper_template  (str)  optional message whispered to the agent before transfer
                             supports {{template}} syntax
"""
from datetime import datetime, timezone

from vaaniq.graph.nodes.base import BaseNode
from vaaniq.core.state import SessionState, Message
from vaaniq.graph.resolver import TemplateResolver


class TransferHumanNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        transfer_to: str = self.config.get("transfer_number", "")
        whisper_template: str = self.config.get("whisper_template", "")

        whisper = ""
        if whisper_template:
            whisper = TemplateResolver.resolve_value(whisper_template, state, self.org_keys)

        now = datetime.now(timezone.utc).isoformat()
        msg: Message = {
            "role": "agent",
            "content": whisper or "Transferring you to a human agent. Please hold.",
            "timestamp": now,
            "node_id": "transfer_human",
        }

        return {
            "messages": [msg],             # reducer appends
            "transfer_initiated": True,
            "transfer_to": transfer_to,
        }
