"""
ConditionNode — LLM-based routing using structured output.

Uses with_structured_output(RouteDecision) to guarantee the LLM returns a
valid route label rather than free text. Falls back to the first route if
the model returns a label that isn't in the configured list.

Config:
    router_prompt  (str)   describes the routing decision to make
    routes         (list)  [{label: str, description: str}]
    provider       (str)   optional — see llm.py
    model          (str)   optional — see llm.py
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from vaaniq.graph.nodes.base import BaseNode
from vaaniq.graph.nodes.llm import get_llm
from vaaniq.graph.state import GraphSessionState


_SYSTEM_TEMPLATE = """\
You are a routing assistant. Based on the conversation, decide which route to take.

{router_prompt}

Available routes:
{routes_text}

You must respond with exactly one of the route labels listed above."""


class _RouteDecision(BaseModel):
    route: str = Field(description="The chosen route label — must exactly match one of the available labels.")


class ConditionNode(BaseNode):
    async def __call__(self, state: GraphSessionState) -> dict:
        routes: list[dict] = self.config["routes"]
        router_prompt: str = self.config.get("router_prompt", "")
        valid_labels = [r["label"].lower() for r in routes]

        routes_text = "\n".join(f"- {r['label']}: {r['description']}" for r in routes)
        system = _SYSTEM_TEMPLATE.format(
            router_prompt=router_prompt,
            routes_text=routes_text,
        )

        history = _build_history(state)
        llm = get_llm(self.config, self.org_keys)
        llm_structured = llm.with_structured_output(_RouteDecision)

        try:
            decision: _RouteDecision = await llm_structured.ainvoke(
                [SystemMessage(content=system)] + history
            )
            route = decision.route.strip().lower()
            if route not in valid_labels:
                route = valid_labels[0]
        except Exception:
            # Fallback: use first route rather than crashing the graph
            route = valid_labels[0]

        return {"route": route, "current_node": "condition"}


def _build_history(state: GraphSessionState) -> list:
    result = []
    for msg in state.get("messages", [])[-10:]:
        if msg["role"] == "user":
            result.append(HumanMessage(content=msg["content"]))
        else:
            result.append(AIMessage(content=msg["content"]))
    return result
