"""
ConditionNode — LLM-based routing.

Looks at the conversation context and classifies which route to take.
Sets state["route"] to the winning label; GraphBuilder wires
add_conditional_edges to read state["route"].

Config:
    router_prompt  (str)   describes the routing decision to make
    routes         (list)  [{label: str, description: str}]
    provider       (str)   optional — see llm.py
    model          (str)   optional — see llm.py
"""
from langchain_core.messages import HumanMessage, SystemMessage

from vaaniq.graph.nodes.base import BaseNode
from vaaniq.core.state import SessionState
from vaaniq.graph.nodes.llm import get_llm


_SYSTEM_TEMPLATE = """\
You are a routing assistant. Based on the conversation below, decide which route to take.

{router_prompt}

Routes:
{routes_text}

Reply with ONLY the route label — nothing else. No explanation, no punctuation."""


class ConditionNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        routes: list[dict] = self.config["routes"]
        router_prompt: str = self.config.get("router_prompt", "")

        routes_text = "\n".join(
            f"- {r['label']}: {r['description']}" for r in routes
        )
        system = _SYSTEM_TEMPLATE.format(
            router_prompt=router_prompt,
            routes_text=routes_text,
        )

        # Build conversation history for context
        history = _build_history(state)

        llm = get_llm(self.config, self.org_keys)
        response = await llm.ainvoke([SystemMessage(content=system)] + history)
        raw: str = response.content.strip().lower()

        # Match to a known label (fallback to first route)
        valid_labels = [r["label"].lower() for r in routes]
        route = raw if raw in valid_labels else valid_labels[0]

        return {"route": route, "current_node": "condition"}


def _build_history(state: SessionState) -> list:
    from langchain_core.messages import AIMessage, HumanMessage as LCHuman
    result = []
    for msg in state.get("messages", [])[-10:]:  # last 10 messages for context
        if msg["role"] == "user":
            result.append(LCHuman(content=msg["content"]))
        else:
            result.append(AIMessage(content=msg["content"]))
    return result
