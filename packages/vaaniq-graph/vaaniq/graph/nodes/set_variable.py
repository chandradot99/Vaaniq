"""
SetVariableNode — set a state field directly without an LLM call.

Config:
    key   (str)  dot-path into state, e.g. "collected.intent" or "route"
    value (any)  literal value or {{template}} expression
"""
from vaaniq.graph.nodes.base import BaseNode
from vaaniq.core.state import SessionState
from vaaniq.graph.resolver import TemplateResolver


class SetVariableNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        key: str = self.config["key"]
        raw_value = self.config["value"]
        value = TemplateResolver.resolve_value(raw_value, state, self.org_keys)

        parts = key.split(".", 1)

        # Nested key: e.g. "collected.intent" → state["collected"]["intent"]
        if len(parts) == 2:
            root, field = parts
            current = dict(state.get(root) or {})
            current[field] = value
            return {root: current}

        # Top-level key: e.g. "route"
        return {key: value}
