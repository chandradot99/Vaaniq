"""
Unit tests for LLM nodes — LLM calls are mocked.

LLMResponseNode, ConditionNode.
CollectDataNode is tested separately (uses interrupt()).
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _state(**kwargs):
    base = {
        "session_id": "sess-1",
        "agent_id": "agent-1",
        "org_id": "org-1",
        "channel": "chat",
        "user_id": "user-1",
        "messages": [],
        "current_node": "start",
        "collected": {},
        "rag_context": "",
        "crm_record": None,
        "tool_calls": [],
        "route": None,
        "transfer_to": None,
        "transfer_initiated": False,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": None,
        "duration_seconds": None,
        "session_ended": False,
        "summary": None,
        "sentiment": None,
        "action_items": [],
        "post_actions_completed": [],
        "error": None,
    }
    base.update(kwargs)
    return base


def _mock_llm(response_text: str):
    """Return a mock LangChain chat model that returns response_text."""
    mock = MagicMock()
    ai_response = MagicMock()
    ai_response.content = response_text
    ai_response.tool_calls = []
    mock.ainvoke = AsyncMock(return_value=ai_response)
    mock.bind_tools = MagicMock(return_value=mock)
    # with_structured_output returns a chain whose ainvoke yields a dict
    # (TypedDict is a plain dict at runtime — ConditionNode uses decision["route"])
    structured_mock = MagicMock()
    structured_mock.ainvoke = AsyncMock(return_value={"route": response_text})
    mock.with_structured_output = MagicMock(return_value=structured_mock)
    return mock


ORG_KEYS = {"openai": "sk-test"}


# ── LLMResponseNode ───────────────────────────────────────────────────────────

async def test_llm_response_adds_message():
    from vaaniq.graph.nodes.llm_response import LLMResponseNode

    mock_llm = _mock_llm("Hello! How can I help you today?")

    with patch("vaaniq.graph.nodes.llm_response.get_llm", return_value=mock_llm):
        node = LLMResponseNode(
            config={"instructions": "You are a helpful assistant."},
            org_keys=ORG_KEYS,
        )
        result = await node(_state())

    assert len(result["messages"]) == 1
    assert result["messages"][0]["role"] == "agent"
    assert result["messages"][0]["content"] == "Hello! How can I help you today?"
    assert result["messages"][0]["node_id"] == "llm_response"
    assert result["current_node"] == "llm_response"


async def test_llm_response_injects_rag_context():
    from vaaniq.graph.nodes.llm_response import LLMResponseNode

    mock_llm = _mock_llm("Based on our policy...")
    captured_messages = []

    async def capture_invoke(messages):
        captured_messages.extend(messages)
        response = MagicMock()
        response.content = "Based on our policy..."
        response.tool_calls = []
        return response

    mock_llm.ainvoke = capture_invoke

    with patch("vaaniq.graph.nodes.llm_response.get_llm", return_value=mock_llm):
        node = LLMResponseNode(
            config={"instructions": "You are an agent.", "rag_enabled": True},
            org_keys=ORG_KEYS,
        )
        await node(_state(rag_context="Refunds are allowed within 30 days."))

    system_content = captured_messages[0].content
    assert "Refunds are allowed within 30 days." in system_content


async def test_llm_response_uses_conversation_history():
    from vaaniq.graph.nodes.llm_response import LLMResponseNode

    mock_llm = _mock_llm("Your order is confirmed.")
    captured_messages = []

    async def capture_invoke(messages):
        captured_messages.extend(messages)
        response = MagicMock()
        response.content = "Your order is confirmed."
        response.tool_calls = []
        return response

    mock_llm.ainvoke = capture_invoke

    with patch("vaaniq.graph.nodes.llm_response.get_llm", return_value=mock_llm):
        node = LLMResponseNode(config={"instructions": "You are an agent."}, org_keys=ORG_KEYS)
        state = _state(messages=[
            {"role": "user",  "content": "What's my order status?", "timestamp": "t1", "node_id": "n1"},
        ])
        await node(state)

    # System message + 1 user message
    assert len(captured_messages) == 2
    assert captured_messages[1].content == "What's my order status?"


async def test_llm_response_no_rag_context_skipped():
    from vaaniq.graph.nodes.llm_response import LLMResponseNode

    mock_llm = _mock_llm("Hi there!")
    captured_messages = []

    async def capture_invoke(messages):
        captured_messages.extend(messages)
        response = MagicMock()
        response.content = "Hi there!"
        response.tool_calls = []
        return response

    mock_llm.ainvoke = capture_invoke

    with patch("vaaniq.graph.nodes.llm_response.get_llm", return_value=mock_llm):
        node = LLMResponseNode(
            config={"instructions": "You are an agent.", "rag_enabled": True},
            org_keys=ORG_KEYS,
        )
        await node(_state(rag_context=""))

    # rag_context is empty — should NOT appear in system prompt
    assert "knowledge base" not in captured_messages[0].content


# ── ConditionNode ─────────────────────────────────────────────────────────────

async def test_condition_sets_route():
    from vaaniq.graph.nodes.condition import ConditionNode

    mock_llm = _mock_llm("booking")

    with patch("vaaniq.graph.nodes.condition.get_llm", return_value=mock_llm):
        node = ConditionNode(
            config={
                "router_prompt": "What does the user want?",
                "routes": [
                    {"label": "booking",  "description": "User wants to book"},
                    {"label": "pricing",  "description": "User wants pricing"},
                ],
            },
            org_keys=ORG_KEYS,
        )
        result = await node(_state())

    assert result["route"] == "booking"


async def test_condition_normalises_to_lowercase():
    from vaaniq.graph.nodes.condition import ConditionNode

    mock_llm = _mock_llm("BOOKING")   # LLM returns uppercase

    with patch("vaaniq.graph.nodes.condition.get_llm", return_value=mock_llm):
        node = ConditionNode(
            config={
                "router_prompt": "Route this",
                "routes": [
                    {"label": "booking", "description": "Book"},
                    {"label": "other",   "description": "Other"},
                ],
            },
            org_keys=ORG_KEYS,
        )
        result = await node(_state())

    assert result["route"] == "booking"


async def test_condition_falls_back_to_first_route_on_unknown():
    from vaaniq.graph.nodes.condition import ConditionNode

    mock_llm = _mock_llm("something_unexpected")

    with patch("vaaniq.graph.nodes.condition.get_llm", return_value=mock_llm):
        node = ConditionNode(
            config={
                "router_prompt": "Route this",
                "routes": [
                    {"label": "booking", "description": "Book"},
                    {"label": "other",   "description": "Other"},
                ],
            },
            org_keys=ORG_KEYS,
        )
        result = await node(_state())

    assert result["route"] == "booking"   # first route is fallback


async def test_condition_includes_conversation_history():
    from vaaniq.graph.nodes.condition import ConditionNode

    mock_llm = _mock_llm("pricing")
    captured = []

    # The condition node calls llm.with_structured_output(...).ainvoke(messages)
    # so we capture from the structured chain, not from llm.ainvoke directly.
    async def capture_invoke(messages):
        captured.extend(messages)
        return {"route": "pricing"}

    mock_llm.with_structured_output.return_value.ainvoke = capture_invoke

    with patch("vaaniq.graph.nodes.condition.get_llm", return_value=mock_llm):
        node = ConditionNode(
            config={
                "router_prompt": "Route this",
                "routes": [{"label": "pricing", "description": "Pricing"}],
            },
            org_keys=ORG_KEYS,
        )
        state = _state(messages=[
            {"role": "user", "content": "How much does it cost?", "timestamp": "t1", "node_id": "n"}
        ])
        await node(state)

    # System message + user message
    assert len(captured) == 2


# ── LLM provider factory ──────────────────────────────────────────────────────

def test_get_llm_openai():
    from vaaniq.graph.nodes.llm import get_llm
    with patch("vaaniq.graph.nodes.llm.ChatOpenAI") as mock_cls:
        get_llm({"model": "gpt-4o-mini"}, {"openai": "sk-test"})
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-test"
        assert call_kwargs["model"] == "gpt-4o-mini"


def test_get_llm_anthropic():
    from vaaniq.graph.nodes.llm import get_llm
    with patch("vaaniq.graph.nodes.llm.ChatAnthropic") as mock_cls:
        get_llm({"provider": "anthropic"}, {"anthropic": "sk-ant-test"})
        mock_cls.assert_called_once()


def test_get_llm_no_key_raises():
    from vaaniq.graph.nodes.llm import get_llm
    with pytest.raises(ValueError, match="No LLM provider"):
        get_llm({}, {})


def test_get_llm_explicit_provider_overrides_autodetect():
    from vaaniq.graph.nodes.llm import get_llm
    with patch("vaaniq.graph.nodes.llm.ChatAnthropic") as mock_cls:
        # Has openai key but explicitly requests anthropic
        get_llm({"provider": "anthropic"}, {"openai": "sk-test", "anthropic": "sk-ant"})
        mock_cls.assert_called_once()
