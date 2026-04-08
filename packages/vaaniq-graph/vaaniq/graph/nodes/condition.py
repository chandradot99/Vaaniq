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
import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from typing import TypedDict

from vaaniq.graph.nodes.base import BaseNode
from vaaniq.graph.nodes.llm import get_llm
from vaaniq.graph.state import GraphSessionState

log = structlog.get_logger()


_SYSTEM_TEMPLATE = """\
You are a routing assistant. Based on the conversation, decide which route to take.

{router_prompt}

Available routes:
{routes_text}

You must respond with exactly one of the route labels listed above."""


class _RouteDecision(TypedDict):
    """TypedDict instead of BaseModel — avoids Pydantic serialization warnings
    when LangGraph checkpoints the structured output response via MemorySaver."""
    route: str


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
            # TypedDict → plain dict at runtime; access with [] not attribute
            route = decision["route"].strip().lower()
            if route not in valid_labels:
                log.warning(
                    "condition_invalid_route",
                    returned=route,
                    valid=valid_labels,
                    fallback=valid_labels[0],
                    session_id=state.get("session_id"),
                )
                route = valid_labels[0]
        except Exception as exc:
            log.warning(
                "condition_llm_error",
                error=str(exc),
                fallback=valid_labels[0],
                session_id=state.get("session_id"),
            )
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
