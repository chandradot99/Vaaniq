"""
In-process compiled graph cache.

LangGraph CompiledStateGraph objects cannot be serialized (Python closures),
so they must live in process memory. This module caches them by
agent_id:graph_version so each agent compiles at most once per process lifetime.

Checkpointer strategy
─────────────────────
The LangGraph checkpointer is baked in at compile time via workflow.compile().
For multi-turn memory (Command(resume=...)) a checkpointer is required.

The caller passes the checkpointer to get_or_compile():
  - Production (voice + chat servers): AsyncPostgresSaver — state survives
    server restarts and can be read by any machine in a multi-instance deployment.
  - Development / testing: pass None → falls back to MemorySaver per agent entry.

IMPORTANT: the checkpointer type must be consistent within a single process run.
If the server starts with PostgresSaver (production), it must be passed on every
call including prewarm. Switching checkpointer types mid-process will return a
graph compiled with a different checkpointer than the caller intends. Restart the
process to pick up a new checkpointer.

Cache invalidation
──────────────────
graph_version is incremented every time graph_config is saved (agent publish).
New version → new cache key → old entry is no longer reachable.
Old entries are collected on server restart.
"""

import asyncio

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

log = structlog.get_logger()


# agent_id:version → (compiled_graph, effective_checkpointer)
_cache: dict[str, tuple[CompiledStateGraph, object]] = {}
_locks: dict[str, asyncio.Lock] = {}
_locks_mu = asyncio.Lock()


async def _get_lock(key: str) -> asyncio.Lock:
    async with _locks_mu:
        if key not in _locks:
            _locks[key] = asyncio.Lock()
        return _locks[key]


async def get_or_compile(
    agent_id: str,
    graph_version: int,
    graph_config: dict,
    org_keys: dict,
    checkpointer=None,
) -> tuple[CompiledStateGraph, object]:
    """
    Return (compiled_graph, checkpointer), compiling on first call.

    The checkpointer is baked into the graph at compile time and also returned
    so callers can read final state (e.g. for finalization after a voice call).

    Args:
        agent_id:      UUID string of the agent.
        graph_version: From agents.graph_version — bumped on every graph publish.
        graph_config:  Raw JSONB from agents.graph_config.
        org_keys:      Decrypted BYOK keys, baked into node constructors at compile.
        checkpointer:  AsyncPostgresSaver (production) or None (dev → MemorySaver).
    """
    key = f"{agent_id}:{graph_version}"

    if key in _cache:
        return _cache[key]

    lock = await _get_lock(key)
    async with lock:
        if key in _cache:
            return _cache[key]

        from naaviq.graph.builder import GraphBuilder

        log.info("graph_cache_miss", agent_id=agent_id, graph_version=graph_version)
        effective = checkpointer or MemorySaver()
        graph = await GraphBuilder().build(graph_config, org_keys, effective)
        _cache[key] = (graph, effective)
        log.info(
            "graph_cache_stored",
            agent_id=agent_id,
            graph_version=graph_version,
            checkpointer_type=type(effective).__name__,
        )

    return _cache[key]


def cache_size() -> int:
    return len(_cache)
