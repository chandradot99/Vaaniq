"""
NODE_REGISTRY — maps graph_config node type strings to handler classes.

To add a new node type:
1. Create vaaniq/graph/nodes/<type>.py with a class extending BaseNode
2. Import it here and add it to NODE_REGISTRY
3. Add the React Flow component in the frontend
"""
from vaaniq.graph.nodes.collect_data import CollectDataNode
from vaaniq.graph.nodes.condition import ConditionNode
from vaaniq.graph.nodes.human_review import HumanReviewNode
from vaaniq.graph.nodes.inbound_message import InboundMessageNode
from vaaniq.graph.nodes.end_session import EndSessionNode
from vaaniq.graph.nodes.http_request import HttpRequestNode
from vaaniq.graph.nodes.llm_response import LLMResponseNode
from vaaniq.graph.nodes.post_session_action import PostSessionActionNode
from vaaniq.graph.nodes.rag_search import RagSearchNode
from vaaniq.graph.nodes.run_tool import RunToolNode
from vaaniq.graph.nodes.set_variable import SetVariableNode
from vaaniq.graph.nodes.transfer_human import TransferHumanNode

NODE_REGISTRY: dict[str, type] = {
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
