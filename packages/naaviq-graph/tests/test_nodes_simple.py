"""
Unit tests for simple nodes — no LLM calls, no DB.

SetVariable, EndSession, TransferHuman, HttpRequest,
RagSearch (stub), PostSessionAction (stub).
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _state(**kwargs):
    base = {
        "session_id": "sess-1",
        "agent_id": "agent-1",
        "org_id": "org-1",
        "channel": "voice",
        "user_id": "+919876543210",
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


ORG_KEYS = {"openai": "sk-test"}


# ── SetVariableNode ───────────────────────────────────────────────────────────

async def test_set_variable_top_level():
    from naaviq.graph.nodes.set_variable import SetVariableNode
    node = SetVariableNode(config={"key": "route", "value": "booking"}, org_keys=ORG_KEYS)
    result = await node(_state())
    assert result == {"route": "booking"}


async def test_set_variable_nested():
    from naaviq.graph.nodes.set_variable import SetVariableNode
    node = SetVariableNode(
        config={"key": "collected.intent", "value": "book_appointment"},
        org_keys=ORG_KEYS,
    )
    result = await node(_state(collected={"name": "Rahul"}))
    assert result["collected"]["intent"] == "book_appointment"
    assert result["collected"]["name"] == "Rahul"   # existing key preserved


async def test_set_variable_with_template():
    from naaviq.graph.nodes.set_variable import SetVariableNode
    node = SetVariableNode(
        config={"key": "collected.greeting", "value": "Hello {{user.id}}"},
        org_keys=ORG_KEYS,
    )
    result = await node(_state())
    assert result["collected"]["greeting"] == "Hello +919876543210"


# ── EndSessionNode ────────────────────────────────────────────────────────────

async def test_end_session_sets_flags():
    from naaviq.graph.nodes.end_session import EndSessionNode
    node = EndSessionNode(config={"farewell_message": "Goodbye!"}, org_keys=ORG_KEYS)
    result = await node(_state())
    assert result["session_ended"] is True
    assert result["end_time"] is not None
    assert len(result["messages"]) == 1
    assert result["messages"][0]["content"] == "Goodbye!"
    assert result["messages"][0]["role"] == "agent"


async def test_end_session_calculates_duration():
    from naaviq.graph.nodes.end_session import EndSessionNode
    node = EndSessionNode(config={"farewell_message": "Bye"}, org_keys=ORG_KEYS)
    state = _state(start_time="2026-04-01T10:00:00+00:00")
    result = await node(state)
    assert result["duration_seconds"] is not None
    assert result["duration_seconds"] >= 0


async def test_end_session_default_farewell():
    from naaviq.graph.nodes.end_session import EndSessionNode
    node = EndSessionNode(config={}, org_keys=ORG_KEYS)
    result = await node(_state())
    assert result["messages"][0]["content"] == "Goodbye!"


# ── TransferHumanNode ─────────────────────────────────────────────────────────

async def test_transfer_human_sets_flags():
    from naaviq.graph.nodes.transfer_human import TransferHumanNode
    node = TransferHumanNode(
        config={"transfer_number": "+911234567890"},
        org_keys=ORG_KEYS,
    )
    result = await node(_state())
    assert result["transfer_initiated"] is True
    assert result["transfer_to"] == "+911234567890"
    assert len(result["messages"]) == 1


async def test_transfer_human_whisper_template():
    from naaviq.graph.nodes.transfer_human import TransferHumanNode
    node = TransferHumanNode(
        config={
            "transfer_number": "+911234567890",
            "whisper_template": "Customer {{collected.name}} wants to book",
        },
        org_keys=ORG_KEYS,
    )
    result = await node(_state(collected={"name": "Amit"}))
    # whisper_template is resolved into whisper_message (for the receiving agent),
    # NOT into messages (which shows the hold message to the caller).
    assert result["whisper_message"] == "Customer Amit wants to book"
    assert result["messages"][0]["content"] == "Transferring you to a human agent. Please hold."


# ── HttpRequestNode ───────────────────────────────────────────────────────────

async def test_http_request_success():
    from naaviq.graph.nodes.http_request import HttpRequestNode

    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "ORD-123", "status": "confirmed"}
    mock_response.raise_for_status = MagicMock()

    node = HttpRequestNode(
        config={
            "method": "POST",
            "url": "https://api.example.com/orders",
            "body": {"name": "{{collected.name}}"},
            "save_response_to": "order_result",
        },
        org_keys=ORG_KEYS,
    )

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value.request = AsyncMock(return_value=mock_response)

        result = await node(_state(collected={"name": "Priya"}))

    assert result["order_result"] == {"id": "ORD-123", "status": "confirmed"}


async def test_http_request_http_error_sets_error_state():
    import httpx

    from naaviq.graph.nodes.http_request import HttpRequestNode

    node = HttpRequestNode(
        config={"method": "GET", "url": "https://api.example.com/fail"},
        org_keys=ORG_KEYS,
    )

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        mock_client.return_value.request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=error_response
            )
        )

        result = await node(_state())

    assert "error" in result
    assert "500" in result["error"]


async def test_http_request_no_save_key_returns_empty():
    from naaviq.graph.nodes.http_request import HttpRequestNode

    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True}
    mock_response.raise_for_status = MagicMock()

    node = HttpRequestNode(
        config={"method": "POST", "url": "https://api.example.com/notify"},
        org_keys=ORG_KEYS,
    )

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value.request = AsyncMock(return_value=mock_response)
        result = await node(_state())

    assert result == {}


# ── RagSearchNode (stub) ──────────────────────────────────────────────────────

async def test_rag_search_no_retriever_returns_empty():
    from naaviq.graph.nodes.rag_search import RagSearchNode
    node = RagSearchNode(config={"top_k": 5}, org_keys={})
    result = await node(_state())
    assert result == {"rag_context": ""}


async def test_rag_search_with_injected_retriever():
    from naaviq.graph.nodes.rag_search import RagSearchNode

    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[
        {"content": "Chunk 1 about refunds"},
        {"content": "Chunk 2 about returns"},
    ])

    node = RagSearchNode(
        config={"top_k": 2, "min_score": 0.5},
        org_keys={"_rag_retriever": mock_retriever},
    )
    state = _state(messages=[
        {"role": "user", "content": "What is your refund policy?", "timestamp": "t1", "node_id": "n1"}
    ])
    result = await node(state)
    assert "Chunk 1" in result["rag_context"]
    assert "Chunk 2" in result["rag_context"]


# ── PostSessionActionNode (stub) ──────────────────────────────────────────────

async def test_post_session_no_dispatcher_skips():
    from naaviq.graph.nodes.post_session_action import PostSessionActionNode
    node = PostSessionActionNode(
        config={"actions": ["create_crm_lead", "send_summary"]},
        org_keys={},
    )
    result = await node(_state())
    # Returns newly completed actions via reducer
    assert result["post_actions_completed"] == ["create_crm_lead", "send_summary"]


async def test_post_session_with_dispatcher():
    from naaviq.graph.nodes.post_session_action import PostSessionActionNode

    dispatched = []
    def mock_dispatcher(action, state):
        dispatched.append(action)

    node = PostSessionActionNode(
        config={"actions": ["create_crm_lead"]},
        org_keys={"_task_dispatcher": mock_dispatcher},
    )
    result = await node(_state())
    assert dispatched == ["create_crm_lead"]
    assert result["post_actions_completed"] == ["create_crm_lead"]


async def test_post_session_skips_already_completed():
    from naaviq.graph.nodes.post_session_action import PostSessionActionNode

    dispatched = []
    def mock_dispatcher(action, state):
        dispatched.append(action)

    node = PostSessionActionNode(
        config={"actions": ["create_crm_lead", "send_summary"]},
        org_keys={"_task_dispatcher": mock_dispatcher},
    )
    # create_crm_lead already done in a previous turn
    result = await node(_state(post_actions_completed=["create_crm_lead"]))
    assert dispatched == ["send_summary"]
    assert result["post_actions_completed"] == ["send_summary"]
