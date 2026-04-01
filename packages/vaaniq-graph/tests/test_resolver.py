"""Unit tests for TemplateResolver — no LLM, no DB required."""
import pytest
from vaaniq.graph.resolver import TemplateResolver


def _state(**kwargs):
    base = {
        "session_id": "sess-1",
        "user_id": "+919876543210",
        "org_id": "org-1",
        "channel": "voice",
        "collected": {},
        "crm_record": None,
        "messages": [],
    }
    base.update(kwargs)
    return base


ORG_KEYS = {"openai": "sk-test", "webhook_secret": "wh-abc"}


# ── Single token — preserves original type ────────────────────────────────────

def test_collected_string():
    state = _state(collected={"name": "Rahul"})
    result = TemplateResolver.resolve_value("{{collected.name}}", state, ORG_KEYS)
    assert result == "Rahul"


def test_collected_int_preserves_type():
    state = _state(collected={"age": 30})
    result = TemplateResolver.resolve_value("{{collected.age}}", state, ORG_KEYS)
    assert result == 30
    assert isinstance(result, int)


def test_user_id():
    state = _state()
    result = TemplateResolver.resolve_value("{{user.id}}", state, ORG_KEYS)
    assert result == "+919876543210"


def test_channel():
    state = _state()
    result = TemplateResolver.resolve_value("{{channel}}", state, ORG_KEYS)
    assert result == "voice"


def test_org_keys():
    state = _state()
    result = TemplateResolver.resolve_value("{{org_keys.webhook_secret}}", state, ORG_KEYS)
    assert result == "wh-abc"


def test_crm_field():
    state = _state(crm_record={"email": "user@example.com", "id": "crm-99"})
    result = TemplateResolver.resolve_value("{{crm.email}}", state, ORG_KEYS)
    assert result == "user@example.com"


def test_top_level_custom_key():
    state = _state(webhook_result={"order_id": "ORD-123"})
    result = TemplateResolver.resolve_value("{{webhook_result.order_id}}", state, ORG_KEYS)
    assert result == "ORD-123"


# ── Mixed string — stringifies replacements ───────────────────────────────────

def test_mixed_string():
    state = _state(collected={"name": "Priya"})
    result = TemplateResolver.resolve_value("Hello {{collected.name}}!", state, ORG_KEYS)
    assert result == "Hello Priya!"


def test_multiple_tokens_in_string():
    state = _state(collected={"name": "Amit", "date": "2026-04-05"})
    result = TemplateResolver.resolve_value(
        "Meeting with {{collected.name}} on {{collected.date}}", state, ORG_KEYS
    )
    assert result == "Meeting with Amit on 2026-04-05"


def test_missing_token_returns_empty_string():
    state = _state(collected={})
    result = TemplateResolver.resolve_value("Hello {{collected.name}}!", state, ORG_KEYS)
    assert result == "Hello !"


# ── resolve() — full config dict ─────────────────────────────────────────────

def test_resolve_dict():
    state = _state(collected={"name": "Riya", "date": "2026-04-10"})
    config = {
        "method": "POST",
        "url": "https://api.example.com/book",
        "body": {
            "name": "{{collected.name}}",
            "date": "{{collected.date}}",
        },
        "timeout_seconds": 10,
    }
    result = TemplateResolver.resolve(config, state, ORG_KEYS)
    assert result["url"] == "https://api.example.com/book"
    assert result["body"]["name"] == "Riya"
    assert result["body"]["date"] == "2026-04-10"
    assert result["timeout_seconds"] == 10   # non-string untouched


def test_resolve_nested_list():
    state = _state(collected={"item": "laptop"})
    config = {"items": ["{{collected.item}}", "phone"]}
    result = TemplateResolver.resolve(config, state, ORG_KEYS)
    assert result["items"] == ["laptop", "phone"]


def test_no_templates_unchanged():
    state = _state()
    config = {"method": "GET", "url": "https://api.example.com"}
    result = TemplateResolver.resolve(config, state, ORG_KEYS)
    assert result == config


# ── Error cases ───────────────────────────────────────────────────────────────

def test_org_keys_without_field_raises():
    state = _state()
    with pytest.raises(ValueError, match="org_keys"):
        TemplateResolver.resolve_value("{{org_keys}}", state, ORG_KEYS)


def test_user_unknown_field_raises():
    state = _state()
    with pytest.raises(ValueError, match="Unknown user field"):
        TemplateResolver.resolve_value("{{user.unknown}}", state, ORG_KEYS)
