"""
CollectDataNode — gather structured fields from the user over multiple turns.

On each turn the node:
  1. Calls interrupt() to receive the latest user message
  2. Parses it to extract the field it asked for last turn
  3. Saves it to state["collected"] (via dict_merge reducer)
  4. If all required fields are collected → returns (edge routes forward)
  5. If fields remain → asks the next question then calls interrupt() again
     to pause until the next user turn

The session handler must call:
  - graph.ainvoke(initial_state, config)           ← first turn
  - graph.ainvoke(Command(resume=user_msg), config) ← every subsequent turn

Config:
    fields  (list)  [{ name, type, prompt, required, validation_prompt? }]

Field types: string | int | float | date | email | phone | bool
"""
import json
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from vaaniq.graph.nodes.base import BaseNode
from vaaniq.core.state import SessionState, Message
from vaaniq.graph.nodes.llm import get_llm


_EXTRACT_SYSTEM = """\
Extract the value of "{field_name}" ({field_type}) from the user message.
{validation_hint}
Reply with a JSON object: {{"value": <extracted value>, "valid": true}} if extraction succeeds,
or {{"value": null, "valid": false, "reason": "<why>"}} if it does not.
Reply with ONLY the JSON — no explanation."""


class CollectDataNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        fields: list[dict] = self.config.get("fields", [])
        collected: dict = dict(state.get("collected") or {})
        now = datetime.now(timezone.utc).isoformat()

        while True:
            pending = _find_pending_field(fields, collected)

            # All required fields collected — continue graph
            if pending is None:
                return {
                    "collected": collected,
                    "current_node": "collect_data",
                }

            # Ask user for the next pending field
            ask_msg: Message = {
                "role": "agent",
                "content": pending["prompt"],
                "timestamp": now,
                "node_id": "collect_data",
            }

            # Pause and wait for user response
            # Session handler resumes with: Command(resume=user_message_text)
            user_response: str = interrupt({
                "type": "collect_question",
                "content": pending["prompt"],
                "field": pending["name"],
            })

            # Extract the field value from the user's response
            extracted = await self._extract(pending, user_response)

            if extracted["valid"]:
                collected[pending["name"]] = extracted["value"]
                # Loop to check if more fields remain
            else:
                # Re-ask with a gentle nudge
                reason = extracted.get("reason", "")
                re_ask = f"Sorry, I didn't quite catch that. {reason} {pending['prompt']}".strip()
                user_response = interrupt({
                    "type": "collect_question",
                    "content": re_ask,
                    "field": pending["name"],
                })
                extracted = await self._extract(pending, user_response)
                if extracted["valid"]:
                    collected[pending["name"]] = extracted["value"]

    async def _extract(self, field: dict, user_message: str) -> dict:
        validation_hint = field.get("validation_prompt", "")
        system = _EXTRACT_SYSTEM.format(
            field_name=field["name"],
            field_type=field.get("type", "string"),
            validation_hint=validation_hint,
        )
        llm = get_llm(self.config, self.org_keys)
        response = await llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=user_message),
        ])
        try:
            return json.loads(response.content)
        except (json.JSONDecodeError, AttributeError):
            return {"value": None, "valid": False, "reason": "Could not parse response"}


def _find_pending_field(fields: list[dict], collected: dict) -> dict | None:
    """Return the first required field not yet in collected, or None if all done."""
    for field in fields:
        if field.get("required", True) and field["name"] not in collected:
            return field
    return None
