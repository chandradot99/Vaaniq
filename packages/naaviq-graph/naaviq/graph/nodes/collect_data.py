"""
CollectDataNode — gather structured fields from the user over multiple turns.

On each turn the node:
  1. Pre-extracts field values from the last user message (skips Q&A for info
     already provided upfront, e.g. "book thursday 5pm")
  2. For each remaining field: asks, waits for reply via interrupt(), extracts
  3. Re-asks once if extraction fails; after two failed attempts accepts the
     raw response to prevent the session from looping forever
  4. When all required fields are collected → returns (edge routes forward)

Config:
    fields  (list)  [{ name, type, prompt, required, validation_prompt? }]

Field types: string | int | float | date | email | phone | bool
"""
import asyncio
import json
from datetime import datetime, timezone

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from naaviq.core.state import SessionState
from naaviq.graph.nodes.base import BaseNode
from naaviq.graph.nodes.llm import get_llm

log = structlog.get_logger()

_EXTRACT_SYSTEM = """\
The assistant asked the user: "{question}"
The user replied. Extract the value of "{field_name}" ({field_type}) from their reply.

Today is {today}.

Rules:
- The user's reply is a direct answer to the question above — treat it as such.
- For string fields: accept whatever the user said as the value. Do not reject unless the reply is completely empty or nonsensical.
- For date/time fields: resolve to ISO 8601 format YYYY-MM-DDTHH:MM using today as the reference. Always use the current year unless the user explicitly said otherwise. If the user mentioned a timezone name (IST, EST, PST, GMT, CET, etc.), convert it to a UTC offset and include it — e.g. "10pm IST" → "2026-04-06T22:00+05:30", "3pm EST" → "2026-04-06T15:00-05:00". If no timezone mentioned, output without offset.
{validation_hint}
Reply with a JSON object: {{"value": <extracted value>, "valid": true}} if extraction succeeds,
or {{"value": null, "valid": false, "reason": "<why>"}} if it truly does not.
Reply with ONLY the JSON — no explanation."""

_PRE_EXTRACT_SYSTEM = """\
The user just sent the following message. Your job is to extract the value of "{field_name}" ({field_type}) \
if it was mentioned — even implicitly or informally.

Today is {today}.

Context about what we are collecting:
{instructions}

Rules:
- The user has NOT been asked for "{field_name}" yet — they volunteered this information upfront.
- For string fields: accept anything the user said that fits. Reject only if truly absent.
- For date/time fields: resolve to ISO 8601 format YYYY-MM-DDTHH:MM using today as the reference. Always use the current year unless the user explicitly said otherwise. If the user mentioned a timezone name (IST, EST, PST, GMT, CET, etc.), convert it to a UTC offset and include it — e.g. "10pm IST" → "2026-04-06T22:00+05:30". If no timezone mentioned, output without offset.
- If the field value is not mentioned at all, reply with valid=false.
{validation_hint}
Reply with a JSON object: {{"value": <extracted value>, "valid": true}} if extraction succeeds,
or {{"value": null, "valid": false, "reason": "<why>"}} if it truly does not.
Reply with ONLY the JSON — no explanation."""


class CollectDataNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        fields: list[dict] = self.config.get("fields", [])
        instructions: str = self.config.get("instructions", "")
        collected: dict = dict(state.get("collected") or {})

        # LangGraph preserves local variable state across interrupt()/resume cycles
        # (the coroutine frame is serialized in the checkpoint), so messages_to_add
        # accumulates across all turns in this collect_data phase and is returned once
        # all fields are done.
        messages_to_add: list = []

        # ── Pre-extraction pass (parallel) ────────────────────────────────────
        # Try extracting every uncollected field from the last user message so
        # that users who provide info upfront ("book thursday 5pm for team meeting")
        # skip those Q&As entirely.
        # All field extractions run concurrently — one LLM call per field in parallel
        # rather than sequentially, which cuts latency from N×LLM to ~1×LLM.
        last_user_msg = next(
            (m["content"] for m in reversed(state.get("messages", [])) if m["role"] == "user"),
            None,
        )
        if last_user_msg:
            pending_fields = [f for f in fields if f["name"] not in collected]
            if pending_fields:
                results = await asyncio.gather(
                    *[self._pre_extract(f, last_user_msg, instructions) for f in pending_fields],
                    return_exceptions=False,
                )
                for field, result in zip(pending_fields, results):
                    if result.get("valid"):
                        collected[field["name"]] = result["value"]

        # ── Q&A loop ──────────────────────────────────────────────────────────
        while True:
            pending = _find_pending_field(fields, collected)

            # All required fields collected — flush Q&A into transcript and continue
            if pending is None:
                return {
                    "collected": collected,
                    "current_node": "collect_data",
                    "messages": messages_to_add,
                }

            now = datetime.now(timezone.utc).isoformat()

            # Record the question as an agent message
            messages_to_add.append({
                "role": "agent",
                "content": pending["prompt"],
                "timestamp": now,
                "node_id": "collect_data",
            })

            # Pause and wait for user response
            user_response: str = interrupt({
                "type": "collect_question",
                "content": pending["prompt"],
                "field": pending["name"],
            })

            # Record the user's answer
            messages_to_add.append({
                "role": "user",
                "content": user_response,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "node_id": "collect_data",
            })

            # Extract the field value from the user's response
            extracted = await self._extract(pending, user_response)

            if extracted["valid"]:
                collected[pending["name"]] = extracted["value"]
                # Loop to check if more fields remain
            else:
                # Re-ask once with a gentle nudge
                reason = extracted.get("reason", "")
                re_ask = f"Sorry, I didn't quite catch that. {reason} {pending['prompt']}".strip()

                messages_to_add.append({
                    "role": "agent",
                    "content": re_ask,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "node_id": "collect_data",
                })

                user_response = interrupt({
                    "type": "collect_question",
                    "content": re_ask,
                    "field": pending["name"],
                })

                messages_to_add.append({
                    "role": "user",
                    "content": user_response,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "node_id": "collect_data",
                })

                extracted = await self._extract(pending, user_response)
                if extracted["valid"]:
                    collected[pending["name"]] = extracted["value"]
                else:
                    # Two failed extraction attempts — accept the raw response rather than
                    # looping forever. Better to have imperfect data than a stuck session.
                    log.warning(
                        "collect_data_accept_raw",
                        field=pending["name"],
                        session_id=state.get("session_id"),
                    )
                    collected[pending["name"]] = user_response

    async def _pre_extract(self, field: dict, user_message: str, instructions: str) -> dict:
        """Extract a field value from the user's initial message (no Q&A question was asked yet)."""
        validation_hint = field.get("validation_prompt", "")
        today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
        system = _PRE_EXTRACT_SYSTEM.format(
            today=today,
            field_name=field["name"],
            field_type=field.get("type", "string"),
            instructions=instructions or "No additional context provided.",
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

    async def _extract(self, field: dict, user_message: str) -> dict:
        validation_hint = field.get("validation_prompt", "")
        today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
        system = _EXTRACT_SYSTEM.format(
            today=today,
            question=field.get("prompt", field["name"]),
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
