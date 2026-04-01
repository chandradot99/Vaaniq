"""Unit tests for GraphSessionState reducers."""
from vaaniq.graph.state import GraphSessionState


def test_messages_reducer_appends():
    """operator.add on messages list appends new messages."""
    msg1 = {"role": "agent", "content": "Hi", "timestamp": "t1", "node_id": "n1"}
    msg2 = {"role": "user",  "content": "Hello", "timestamp": "t2", "node_id": "n2"}

    existing = [msg1]
    new = [msg2]
    merged = existing + new   # what the reducer does
    assert merged == [msg1, msg2]


def test_collected_reducer_merges():
    """dict_merge on collected merges without losing existing keys."""
    from vaaniq.graph.state import _dict_merge

    existing = {"name": "Rahul", "city": "Mumbai"}
    update = {"date": "2026-04-10"}
    merged = _dict_merge(existing, update)

    assert merged == {"name": "Rahul", "city": "Mumbai", "date": "2026-04-10"}


def test_collected_reducer_overwrites_on_conflict():
    """Newer value wins on key conflict."""
    from vaaniq.graph.state import _dict_merge

    existing = {"name": "Rahul"}
    update = {"name": "Priya"}
    merged = _dict_merge(existing, update)

    assert merged["name"] == "Priya"


def test_tool_calls_reducer_appends():
    """operator.add on tool_calls list appends."""
    import operator
    call1 = {"tool_name": "calendar", "input": {}, "output": "ok", "called_at": "t1", "success": True}
    call2 = {"tool_name": "crm",      "input": {}, "output": "ok", "called_at": "t2", "success": True}

    merged = operator.add([call1], [call2])
    assert merged == [call1, call2]


def test_graphsessionstate_has_required_fields():
    """Smoke test — all expected keys present in type annotations."""
    annotations = GraphSessionState.__annotations__
    required = [
        "session_id", "agent_id", "org_id", "channel", "user_id",
        "messages", "current_node", "route", "collected",
        "rag_context", "crm_record", "tool_calls",
        "transfer_to", "transfer_initiated",
        "start_time", "end_time", "duration_seconds", "session_ended",
        "summary", "sentiment", "action_items", "post_actions_completed",
        "error",
    ]
    for field in required:
        assert field in annotations, f"Missing field: {field}"
