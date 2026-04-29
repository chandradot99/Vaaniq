"""
NODE_REGISTRY — maps graph_config node type strings to handler classes.

To add a new node type:
1. Create naaviq/graph/nodes/<type>.py with a class extending BaseNode
2. Import it here and add it to NODE_REGISTRY
3. Add the React Flow component in the frontend
"""
from naaviq.graph.nodes.collect_data import CollectDataNode
from naaviq.graph.nodes.condition import ConditionNode
from naaviq.graph.nodes.end_session import EndSessionNode
from naaviq.graph.nodes.http_request import HttpRequestNode
from naaviq.graph.nodes.human_review import HumanReviewNode
from naaviq.graph.nodes.inbound_message import InboundMessageNode
from naaviq.graph.nodes.llm_response import LLMResponseNode
from naaviq.graph.nodes.post_session_action import PostSessionActionNode
from naaviq.graph.nodes.rag_search import RagSearchNode
from naaviq.graph.nodes.run_tool import RunToolNode
from naaviq.graph.nodes.set_variable import SetVariableNode
from naaviq.graph.nodes.start import StartNode
from naaviq.graph.nodes.transfer_human import TransferHumanNode

NODE_REGISTRY: dict[str, type] = {
    # Entry
    "start":               StartNode,
    # Input
    "inbound_message":     InboundMessageNode,
    # Logic
    "llm_response":        LLMResponseNode,
    "condition":           ConditionNode,
    "collect_data":        CollectDataNode,
    "set_variable":        SetVariableNode,
    # Human-in-the-loop
    "human_review":        HumanReviewNode,
    # Action
    "run_tool":            RunToolNode,
    "http_request":        HttpRequestNode,
    "transfer_human":      TransferHumanNode,
    "end_session":         EndSessionNode,
    "post_session_action": PostSessionActionNode,
    # Data
    "rag_search":          RagSearchNode,
}

__all__ = ["NODE_REGISTRY"]
