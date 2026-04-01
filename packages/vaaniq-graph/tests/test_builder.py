"""
Unit tests for GraphBuilder — uses InMemorySaver, no PostgreSQL required.
"""
import pytest
from langgraph.checkpoint.memory import MemorySaver


SIMPLE_GRAPH = {
    "entry_point": "greet",
    "nodes": [
        {
            "id": "greet",
            "type": "set_variable",
            "config": {"key": "route", "value": "done"},
        },
        {
            "id": "farewell",
            "type": "end_session",
            "config": {"farewell_message": "Goodbye!"},
        },
    ],
    "edges": [
        {"id": "e1", "source": "greet",   "target": "farewell"},
        {"id": "e2", "source": "farewell", "target": "end"},
    ],
}

CONDITIONAL_GRAPH = {
    "entry_point": "router",
    "nodes": [
        {
            "id": "router",
            "type": "set_variable",
            "config": {"key": "route", "value": "path_a"},
        },
        {
            "id": "path_a",
            "type": "end_session",
            "config": {"farewell_message": "Path A"},
        },
        {
            "id": "path_b",
            "type": "end_session",
            "config": {"farewell_message": "Path B"},
        },
    ],
    "edges": [
        {"id": "e1", "source": "router", "target": "path_a", "condition": "path_a"},
        {"id": "e2", "source": "router", "target": "path_b", "condition": "path_b"},
        {"id": "e3", "source": "path_a", "target": "end"},
        {"id": "e4", "source": "path_b", "target": "end"},
    ],
}


def _initial_state(**kwargs):
    from datetime import datetime, timezone
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


# ── Build validation ──────────────────────────────────────────────────────────

async def test_build_simple_graph():
    from vaaniq.graph.builder import GraphBuilder
    graph = await GraphBuilder().build(SIMPLE_GRAPH, org_keys={}, checkpointer=MemorySaver())
    assert graph is not None


async def test_build_unknown_node_type_raises():
    from vaaniq.graph.builder import GraphBuilder
    bad_graph = {
        "entry_point": "n1",
        "nodes": [{"id": "n1", "type": "does_not_exist", "config": {}}],
        "edges": [],
    }
    with pytest.raises(ValueError, match="Unknown node type"):
        await GraphBuilder().build(bad_graph, org_keys={})


async def test_build_missing_entry_point_raises():
    from vaaniq.graph.builder import GraphBuilder
    bad_graph = {"nodes": [], "edges": []}
    with pytest.raises(ValueError, match="entry_point"):
        await GraphBuilder().build(bad_graph, org_keys={})


# ── Graph execution ───────────────────────────────────────────────────────────

async def test_simple_graph_runs_to_completion():
    from vaaniq.graph.builder import GraphBuilder

    graph = await GraphBuilder().build(SIMPLE_GRAPH, org_keys={}, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "test-thread-1"}}
    result = await graph.ainvoke(_initial_state(), config=config)

    assert result["session_ended"] is True
    assert any(m["content"] == "Goodbye!" for m in result["messages"])


async def test_conditional_graph_routes_correctly():
    from vaaniq.graph.builder import GraphBuilder

    graph = await GraphBuilder().build(CONDITIONAL_GRAPH, org_keys={}, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "test-thread-2"}}
    result = await graph.ainvoke(_initial_state(), config=config)

    # Router sets route="path_a", so path_a node should run
    assert result["session_ended"] is True
    assert any(m["content"] == "Path A" for m in result["messages"])


async def test_graph_without_checkpointer():
    """Graph should compile and run without a checkpointer (stateless mode)."""
    from vaaniq.graph.builder import GraphBuilder

    graph = await GraphBuilder().build(SIMPLE_GRAPH, org_keys={}, checkpointer=None)
    result = await graph.ainvoke(_initial_state())

    assert result["session_ended"] is True


async def test_empty_nodes_list():
    """Entry point with no edges terminates immediately."""
    from vaaniq.graph.builder import GraphBuilder
    graph_config = {
        "entry_point": "only_node",
        "nodes": [
            {"id": "only_node", "type": "end_session", "config": {"farewell_message": "Done"}}
        ],
        "edges": [{"id": "e1", "source": "only_node", "target": "end"}],
    }
    graph = await GraphBuilder().build(graph_config, org_keys={})
    result = await graph.ainvoke(_initial_state())
    assert result["session_ended"] is True
