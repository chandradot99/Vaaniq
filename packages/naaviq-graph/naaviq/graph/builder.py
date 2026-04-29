"""
GraphBuilder — deserializes a graph_config JSON dict into a compiled LangGraph.

Usage:
    builder = GraphBuilder()
    graph = await builder.build(agent.graph_config, org_keys, checkpointer)

    # First turn
    result = await graph.ainvoke(initial_state, config={"configurable": {"thread_id": session_id}})

    # Subsequent turns (resume after interrupt)
    from langgraph.types import Command
    result = await graph.ainvoke(
        Command(resume=user_message),
        config={"configurable": {"thread_id": session_id}},
    )
"""
from collections import defaultdict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from naaviq.graph.nodes import NODE_REGISTRY
from naaviq.graph.state import GraphSessionState


class GraphBuilder:
    async def build(
        self,
        graph_config: dict,
        org_keys: dict,
        checkpointer=None,
    ) -> CompiledStateGraph:
        """
        Build and compile a LangGraph from a graph_config dict.

        Args:
            graph_config:  the JSONB value from agents.graph_config
            org_keys:      decrypted BYOK keys for this org, e.g. {"openai": "sk-..."}
            checkpointer:  AsyncPostgresSaver (production) or InMemorySaver (dev/tests).
                           Required for multi-turn memory via interrupt().
                           Call checkpointer.setup() once before passing it in.
        """
        workflow = StateGraph(GraphSessionState)

        # Validate graph structure up-front for clear error messages
        node_ids = {n["id"] for n in graph_config.get("nodes", [])}
        entry = graph_config.get("entry_point")
        if not entry:
            raise ValueError("graph_config must have an 'entry_point'")
        if entry not in node_ids:
            raise ValueError(
                f"entry_point {entry!r} does not match any node id. "
                f"Available node ids: {sorted(node_ids)}"
            )
        # Register nodes
        for node in graph_config.get("nodes", []):
            node_type = node["type"]
            if node_type not in NODE_REGISTRY:
                raise ValueError(
                    f"Unknown node type {node_type!r}. "
                    f"Available: {sorted(NODE_REGISTRY)}"
                )
            handler = NODE_REGISTRY[node_type](
                config=node.get("config", {}),
                org_keys=org_keys,
            )
            workflow.add_node(node["id"], handler)

        # Separate direct edges from conditional edges (grouped by source)
        conditional: dict[str, list[dict]] = defaultdict(list)

        for edge in graph_config.get("edges", []):
            source = edge["source"]
            target = edge["target"]
            # "end" is the legacy sentinel for LangGraph END — but only when no real
            # node with that id exists. If the graph has an actual node named "end",
            # route to it normally so it can execute (e.g. an end_session node).
            lc_target = END if (target == "end" and "end" not in node_ids) else target

            if "condition" in edge:
                conditional[source].append(edge)
            else:
                workflow.add_edge(source, lc_target)

        # Add conditional edges — condition node writes state["route"] (always lowercase)
        # Mapping keys are lowercased to match: condition.py lowercases route labels before
        # writing to state, so the lookup must use the same casing.
        for source, edges in conditional.items():
            mapping = {
                e["condition"].lower(): (END if (e["target"] == "end" and "end" not in node_ids) else e["target"])
                for e in edges
            }
            workflow.add_conditional_edges(
                source,
                lambda state: (state.get("route") or "").lower(),
                mapping,
            )

        workflow.add_edge(START, entry)

        return workflow.compile(checkpointer=checkpointer)
