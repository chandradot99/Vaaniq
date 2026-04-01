"""
RagSearchNode — search the agent's knowledge base and write results
to state["rag_context"] for the next llm_response node to use.

Full implementation lives in vaaniq-rag. This node calls the RAG
pipeline via a registered retriever that is injected at build time.

Config:
    top_k      (int)    number of chunks to retrieve, default 5
    min_score  (float)  minimum similarity score, default 0.7
    query      (str)    optional explicit query; if omitted the last
                        user message is used as the query
"""
from vaaniq.graph.nodes.base import BaseNode
from vaaniq.core.state import SessionState


class RagSearchNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        # Retriever injected via org_keys["_rag_retriever"] at build time
        # when vaaniq-rag is wired in. No-op if not present.
        retriever = self.org_keys.get("_rag_retriever")
        if retriever is None:
            return {"rag_context": ""}

        top_k: int = int(self.config.get("top_k", 5))
        min_score: float = float(self.config.get("min_score", 0.7))

        query = self.config.get("query") or _last_user_message(state)
        if not query:
            return {"rag_context": ""}

        results = await retriever.retrieve(query, top_k=top_k, min_score=min_score)
        context = "\n\n".join(r["content"] for r in results)
        return {"rag_context": context}


def _last_user_message(state: SessionState) -> str:
    for msg in reversed(state.get("messages", [])):
        if msg["role"] == "user":
            return msg["content"]
    return ""
