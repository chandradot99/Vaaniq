"""
Shared helpers for provider implementations.

Kept here to avoid duplicating the same extract_key / resolve_model logic
across every provider file.
"""

from __future__ import annotations

import structlog

from vaaniq.voice.exceptions import MissingAPIKeyError
from vaaniq.voice.providers.base import ModelInfo

log = structlog.get_logger()


def extract_key(org_keys: dict, provider: str) -> str:
    """
    Pull the API key for `provider` out of org_keys.

    org_keys values can be either a raw string ("sk-abc...") or a dict
    {"api_key": "sk-abc..."} — both are normalised here.

    Raises MissingAPIKeyError if no usable key is found.
    """
    value = org_keys.get(provider)
    if not value:
        raise MissingAPIKeyError(provider)
    if isinstance(value, dict):
        value = value.get("api_key", "")
    if not value:
        raise MissingAPIKeyError(provider)
    return str(value)


def resolve_model(
    requested: str | None,
    valid_models: list[ModelInfo],
    default_id: str,
    provider_label: str,
) -> str:
    """
    Return `requested` if it is in the valid model set, otherwise `default_id`.

    Logs a warning when an unrecognised model is replaced so operators can
    find and fix stale agent configs without the call failing silently.
    """
    if not requested:
        return default_id
    valid_ids = {m.id for m in valid_models}
    if requested in valid_ids:
        return requested
    log.warning(
        f"{provider_label}_invalid_model_fallback",
        requested=requested,
        fallback=default_id,
    )
    return default_id
