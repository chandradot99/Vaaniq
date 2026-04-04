"""
SetVariableNode — set a state field directly without an LLM call.

Config:
    key   (str)  dot-path into state, e.g. "collected.intent" or "route"
    value (any)  literal value or {{template}} expression
"""
import structlog

from vaaniq.graph.nodes.base import BaseNode, PROTECTED_STATE_KEYS
from vaaniq.core.state import SessionState
from vaaniq.graph.resolver import TemplateResolver

log = structlog.get_logger()


class SetVariableNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        key: str = self.config["key"]
        raw_value = self.config["value"]

        parts = key.split(".", 1)
        root = parts[0]

        # Guard against writing into protected system keys
        if root in PROTECTED_STATE_KEYS:
            error_msg = f"set_variable: '{root}' is a protected state key and cannot be overwritten."
            log.error("set_variable_protected_key", key=key, session_id=state.get("session_id"))
            return {"error": error_msg}

        value = TemplateResolver.resolve_value(raw_value, state, self.org_keys)

        # Nested key: e.g. "collected.intent" → state["collected"]["intent"]
        if len(parts) == 2:
            _, field = parts
            current = dict(state.get(root) or {})
            current[field] = value
            return {root: current}

        # Top-level key: e.g. "route"
        return {key: value}
