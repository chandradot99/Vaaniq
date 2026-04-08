"""
In-process compiled graph cache.

LangGraph CompiledStateGraph objects cannot be serialized (Python closures),
so they must live in process memory. This module caches them by
agent_id:graph_version so each agent compiles at most once per process lifetime.

Checkpointer strategy
─────────────────────
The LangGraph checkpointer is baked in at compile time via workflow.compile().
For voice calls, multi-turn memory (Command(resume=...)) requires a checkpointer.

We create ONE MemorySaver per cached graph entry and share it across all
concurrent calls to that agent. This is safe because:
  - MemorySaver stores state keyed by thread_id
  - Each call uses thread_id = "{org_id}:{session_id}" (globally unique)
  - Concurrent calls to the same agent use different thread_ids → no contamination

Memory usage: each call's state is a few KB. Accumulated state lives until
server restart. Acceptable for voice (short-lived sessions, moderate call volume).

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

# agent_id:version → (compiled_graph, shared_memory_saver)
_cache: dict[str, tuple[CompiledStateGraph, MemorySaver]] = {}
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
    checkpointer=None,  # ignored — cache owns the MemorySaver; param kept for API compat
) -> tuple[CompiledStateGraph, MemorySaver]:
    """
    Return (compiled_graph, shared_memory_saver), compiling on first call.

    The returned MemorySaver is shared across all calls for this agent version.
    Each call must use a unique thread_id to avoid state contamination.

    Args:
        agent_id:      UUID string of the agent.
        graph_version: From agents.graph_version — bumped on every graph publish.
        graph_config:  Raw JSONB from agents.graph_config.
        org_keys:      Decrypted BYOK keys, baked into node constructors at compile.
        checkpointer:  Ignored. Kept for call-site compatibility during migration.
    """
    key = f"{agent_id}:{graph_version}"

    if key in _cache:
        return _cache[key]

    lock = await _get_lock(key)
    async with lock:
        if key in _cache:
            return _cache[key]

        from vaaniq.graph.builder import GraphBuilder

        log.info("graph_cache_miss", agent_id=agent_id, graph_version=graph_version)
        memory_saver = MemorySaver()
        graph = await GraphBuilder().build(graph_config, org_keys, memory_saver)
        _cache[key] = (graph, memory_saver)
        log.info("graph_cache_stored", agent_id=agent_id, graph_version=graph_version)

    return _cache[key]


def cache_size() -> int:
    return len(_cache)
