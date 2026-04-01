"""
LLMResponseNode — the main agent response node.

Calls an LLM with the system instructions, conversation history, and
optionally RAG context.

Tool support will be wired in when vaaniq-tools is implemented.

Config:
    instructions  (str)    system prompt / agent persona
    rag_enabled   (bool)   inject state["rag_context"] into system prompt
    voice_id      (str)    passed through to TTS layer (not used here)
    provider      (str)    optional — see llm.py
    model         (str)    optional — see llm.py
    temperature   (float)  optional — see llm.py
"""
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from vaaniq.graph.nodes.base import BaseNode
from vaaniq.core.state import SessionState, Message
from vaaniq.graph.nodes.llm import get_llm


class LLMResponseNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        instructions: str = self.config.get("instructions", "You are a helpful assistant.")
        rag_enabled: bool = self.config.get("rag_enabled", False)

        system_parts = [instructions]
        if rag_enabled and state.get("rag_context"):
            system_parts.append(
                f"\n\nRelevant context from knowledge base:\n{state['rag_context']}"
            )
        system = "\n".join(system_parts)

        llm = get_llm(self.config, self.org_keys)
        lc_messages = [SystemMessage(content=system)] + _to_lc_messages(state)
        response = await llm.ainvoke(lc_messages)

        now = datetime.now(timezone.utc).isoformat()
        agent_msg: Message = {
            "role": "agent",
            "content": response.content,
            "timestamp": now,
            "node_id": "llm_response",
        }

        return {
            "messages": [agent_msg],    # reducer appends
            "current_node": "llm_response",
        }


def _to_lc_messages(state: SessionState) -> list:
    result = []
    for msg in state.get("messages", [])[-20:]:
        if msg["role"] == "user":
            result.append(HumanMessage(content=msg["content"]))
        else:
            result.append(AIMessage(content=msg["content"]))
    return result
