"""
Template variable resolver.

Resolves {{variable}} placeholders in node config values against
the current SessionState and org_keys at call time.

Supported syntax:
  {{collected.name}}       → state["collected"]["name"]
  {{crm.email}}            → state["crm_record"]["email"]
  {{user.id}}              → state["user_id"]
  {{channel}}              → state["channel"]
  {{org_keys.api_key}}     → org_keys["api_key"]
  {{webhook_result.id}}    → state["webhook_result"]["id"]  (any top-level key)
  {{some.nested.key}}      → state["some"]["nested"]["key"]
"""
import re
from typing import Any

from vaaniq.core.state import SessionState

_PATTERN = re.compile(r"\{\{([^}]+)\}\}")

# Maps first segment of a template path → how to resolve the root
_CRM_KEY = "crm"
_COLLECTED_KEY = "collected"
_USER_KEY = "user"
_ORG_KEYS_KEY = "org_keys"

# State fields that use a different key in SessionState
_USER_FIELD_MAP = {
    "id": "user_id",
    "org": "org_id",
    "session": "session_id",
    "channel": "channel",
}


def _get_nested(obj: Any, parts: list[str]) -> Any:
    """Walk a chain of dict keys; returns None if any key is missing."""
    for part in parts:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
        if obj is None:
            return None
    return obj


def _resolve_token(token: str, state: SessionState, org_keys: dict) -> Any:
    """Resolve a single {{token}} to its runtime value."""
    parts = token.strip().split(".")

    root = parts[0]
    rest = parts[1:]

    # {{org_keys.X}} → org_keys["X"]
    if root == _ORG_KEYS_KEY:
        if not rest:
            raise ValueError("{{org_keys}} requires a key: {{org_keys.my_key}}")
        return _get_nested(org_keys, rest)

    # {{collected.X}} → state["collected"]["X"]
    if root == _COLLECTED_KEY:
        if not rest:
            raise ValueError("{{collected}} requires a field: {{collected.name}}")
        return _get_nested(state.get("collected", {}), rest)

    # {{crm.X}} → state["crm_record"]["X"]
    if root == _CRM_KEY:
        if not rest:
            raise ValueError("{{crm}} requires a field: {{crm.email}}")
        return _get_nested(state.get("crm_record") or {}, rest)

    # {{user.X}} → maps to flat state fields
    if root == _USER_KEY:
        if not rest:
            raise ValueError("{{user}} requires a field: {{user.id}}")
        field = _USER_FIELD_MAP.get(rest[0])
        if field is None:
            raise ValueError(f"Unknown user field: {{{{user.{rest[0]}}}}}")
        return state.get(field)

    # {{channel}} or any other top-level single key
    if not rest:
        return state.get(root)

    # {{X.Y.Z}} → state["X"]["Y"]["Z"]
    return _get_nested(state.get(root, {}), rest)


def _resolve_value(value: Any, state: SessionState, org_keys: dict) -> Any:
    """Recursively resolve templates in a value (str, dict, list, or scalar)."""
    if isinstance(value, str):
        tokens = _PATTERN.findall(value)
        if not tokens:
            return value
        # If the whole string is one token, return the resolved value as-is
        # (preserves non-string types like int, dict, list)
        if value.strip() == f"{{{{{tokens[0]}}}}}":
            return _resolve_token(tokens[0], state, org_keys)
        # Multiple tokens or mixed string — stringify each replacement
        def replacer(match: re.Match) -> str:
            resolved = _resolve_token(match.group(1), state, org_keys)
            return str(resolved) if resolved is not None else ""
        return _PATTERN.sub(replacer, value)

    if isinstance(value, dict):
        return {k: _resolve_value(v, state, org_keys) for k, v in value.items()}

    if isinstance(value, list):
        return [_resolve_value(item, state, org_keys) for item in value]

    return value


class TemplateResolver:
    """Resolves {{template}} variables in node config dicts."""

    @staticmethod
    def resolve(config: dict, state: SessionState, org_keys: dict) -> dict:
        """Return a copy of config with all template variables resolved."""
        return {k: _resolve_value(v, state, org_keys) for k, v in config.items()}

    @staticmethod
    def resolve_value(value: Any, state: SessionState, org_keys: dict) -> Any:
        """Resolve templates in a single value (not a full config dict)."""
        return _resolve_value(value, state, org_keys)
