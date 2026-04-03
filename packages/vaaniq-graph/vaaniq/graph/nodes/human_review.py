"""
HumanReviewNode — pause graph execution and wait for human approval.

Uses LangGraph's interrupt() to suspend the graph at this node. The chat
service surfaces the pending_info dict to the frontend as a special message
type. When the user clicks Approve or Reject, the chat service resumes with:

    Command(resume={"decision": "approve"})   or
    Command(resume={"decision": "reject"})

The node then writes state["route"] = "approve" | "reject", which the
conditional edges downstream use for routing.

This requires a checkpointer (AsyncPostgresSaver in production) — the graph
state must be persisted between the interrupt and the resume. The node will
raise a RuntimeError at graph-compile time if no checkpointer is configured.

Config:
    message           (str)   text shown to the reviewer in the approval UI
    context_variable  (str)   optional — name of a collected field whose value
                               is shown alongside the approval message, so the
                               reviewer has context (e.g. show email body before
                               approving the send)
"""
from langgraph.types import interrupt

from vaaniq.graph.nodes.base import BaseNode
from vaaniq.graph.state import GraphSessionState


class HumanReviewNode(BaseNode):
    async def __call__(self, state: GraphSessionState) -> dict:
        message: str = self.config.get("message", "Please review and approve this action.")
        context_variable: str | None = self.config.get("context_variable")

        pending_info: dict = {
            "type": "human_review",
            "message": message,
        }
        if context_variable:
            pending_info["context"] = state.get("collected", {}).get(context_variable)

        # interrupt() suspends the graph here and stores state in the checkpointer.
        # Execution resumes when the service calls graph.ainvoke(Command(resume=...)).
        # The resume value can be:
        #   {"decision": "approve"} or {"decision": "reject"}  — from structured clients
        #   "approve" or "reject"                              — from the chat test panel
        decision = interrupt(pending_info)

        if isinstance(decision, dict):
            route = decision.get("decision", "reject").lower()
        elif isinstance(decision, str):
            route = decision.strip().lower()
        else:
            route = "reject"

        if route not in ("approve", "reject"):
            route = "reject"

        return {"route": route, "current_node": "human_review"}
