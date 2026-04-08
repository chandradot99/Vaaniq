# Vaaniq — Voice Infrastructure & Latency Plan

Active engineering plan. Update status as phases complete. Do not track routine bug fixes here — only architectural changes.

---

## Context

Current state: voice pipeline runs inside `vaaniq-server` (Railway), compiled cold per call. Every call spends ~1.5s before the agent says the first word — building the pipeline, loading the VAD model, connecting to Deepgram and Cartesia. The goal is to bring this down to <400ms TTFG (time to first greeting) for outbound calls and <600ms for inbound.

Measured cold-start breakdown (from production logs):
```
Silero VAD load         100ms
pipeline build          ~400ms
Deepgram WS connect     ~900ms   ← biggest cost
Cartesia WS connect     ~80ms
─────────────────────────────
Total before turn 0     ~1.58s
```

---

## Phase 1 — In-process graph compile cache

**Status:** Done (2026-04-08)  
**Effort:** 1–2 hrs  
**Latency saved:** 50–200ms/call (eliminates per-call GraphBuilder compilation)

### What

`GraphBuilder().build()` recompiles the LangGraph from `graph_config` JSON on every call. Compiled `CompiledStateGraph` objects cannot be serialized (contain Python closures), so they can't be stored in Redis or DB. Cache them in process memory instead.

### Implementation

Add `GraphCache` to `vaaniq-graph`:

```python
# packages/vaaniq-graph/vaaniq/graph/cache.py
import asyncio
from vaaniq.graph.builder import GraphBuilder

_cache: dict[str, object] = {}   # "agent_id:version" → CompiledStateGraph
_lock = asyncio.Lock()

async def get_or_compile(agent_id: str, version: int, graph_config: dict,
                          org_keys: dict, checkpointer) -> object:
    key = f"{agent_id}:{version}"
    if key in _cache:
        return _cache[key]
    async with _lock:
        if key not in _cache:   # double-check after lock
            _cache[key] = await GraphBuilder().build(graph_config, org_keys, checkpointer)
        return _cache[key]

def invalidate(agent_id: str) -> None:
    """Call on agent publish — drops all versions for this agent."""
    for key in [k for k in _cache if k.startswith(f"{agent_id}:")]:
        del _cache[key]
```

Add `graph_version: int` column to `agents` table (migration 0009). Increment on every agent publish. Cache key `agent_id:version` auto-invalidates on new deploy — no explicit signal needed.

### Files

- `packages/vaaniq-graph/vaaniq/graph/cache.py` (new)
- `packages/vaaniq-server/vaaniq/server/migrations/versions/0009_add_graph_version_to_agents.py` (new)
- `packages/vaaniq-server/vaaniq/server/agents/service.py` — bump `graph_version` on publish
- `packages/vaaniq-voice/vaaniq/voice/pipeline/builder.py` — call `get_or_compile` instead of `GraphBuilder().build()`

---

## Phase 2 — VAD pre-load + startup pre-compile

**Status:** Done (2026-04-08)  
**Effort:** 1 hr  
**Latency saved:** 100ms/call (VAD) + eliminates compile latency on first call per agent

### What

Two things happen at cold start that should happen at server startup instead:
1. Silero VAD model loads from disk (~100ms per call — paid by every caller)
2. First call to any agent compiles its graph (paid by that caller, not subsequent ones)

### Implementation

**VAD singleton** — create once at startup, share across all pipeline builds:

```python
# packages/vaaniq-voice/vaaniq/voice/services/vad.py
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from vaaniq.voice.constants import VAD_CONFIDENCE, VAD_START_SECS, VAD_STOP_SECS, VAD_MIN_VOLUME

_vad: SileroVADAnalyzer | None = None

def get_vad_analyzer() -> SileroVADAnalyzer:
    global _vad
    if _vad is None:
        _vad = SileroVADAnalyzer(params=VADParams(
            confidence=VAD_CONFIDENCE,
            start_secs=VAD_START_SECS,
            stop_secs=VAD_STOP_SECS,
            min_volume=VAD_MIN_VOLUME,
        ))
    return _vad
```

**Startup pre-compile** — voice server FastAPI lifespan fetches all active agents and pre-warms the graph cache:

```python
# vaaniq-voice-server startup
async def startup():
    from vaaniq.graph.cache import get_or_compile
    agents = await fetch_all_active_agents()   # HTTP call to vaaniq-server
    for agent in agents:
        await get_or_compile(agent.id, agent.graph_version, agent.graph_config, {}, None)
    log.info("graph_cache_warmed", count=len(agents))
```

### Files

- `packages/vaaniq-voice/vaaniq/voice/services/vad.py` (new)
- `packages/vaaniq-voice/vaaniq/voice/pipeline/builder.py` — use `get_vad_analyzer()` instead of constructing inline

---

## Phase 3 — Separate voice server on Fly.io iad

**Status:** Not started  
**Effort:** 3–4 hrs  
**Latency saved:** 30–50ms/call (geographic co-location with Twilio's US media edge)  
**Cost saved:** ~$70/month (Fly.io always-on ~$12/month vs Railway always-on ~$87/month)

### Why separate

Twilio's US media edge is in **Ashburn, VA (iad)**. Fly.io has machines in `iad`. Running the Pipecat WebSocket server there eliminates an unnecessary network hop on every audio packet. The voice server also competes with REST API traffic for CPU/memory on the current Railway dyno.

### Architecture after split

```
Twilio ─────────────────────────────────────────────────────────────────┐
                                                                         │
       WebSocket (audio)                                                  │
              ↓                                                           │
  ┌─────────────────────────┐   HTTP (context + finalize)  ┌────────────────────────┐
  │  vaaniq-voice-server    │ ──────────────────────────▶  │  vaaniq-server         │
  │  Fly.io iad             │ ◀──────────────────────────  │  Railway               │
  │  Always-on, 1vCPU/2GB  │                               │  REST APIs, DB, auth   │
  │  ~$12/month             │                               │                        │
  └─────────────────────────┘                               └────────────────────────┘
              │
      Deepgram / Cartesia / LLM (external APIs)
```

### What changes

`vaaniq-voice-server` is a thin FastAPI app that mounts **only** the webhook routes. It replaces direct DB imports with two HTTP calls to `vaaniq-server`:

| Currently | After split |
|---|---|
| `from vaaniq.server.voice.context_builder import build_voice_context` | `GET /internal/voice/context/{session_id}` |
| `from vaaniq.server.voice.finalization import finalize_voice_session` | `POST /internal/voice/finalize` |

`vaaniq-server` gains two internal endpoints (no auth — internal network only, not public):
- `GET /internal/voice/context/{session_id}` — returns full `VoiceCallContext` as JSON
- `POST /internal/voice/finalize` — accepts transcript + events, saves to DB

### Files

- `packages/vaaniq-voice-server/` (new package — thin FastAPI, just webhooks)
- `packages/vaaniq-server/vaaniq/server/voice/router.py` — add `/internal/voice/context` and `/internal/voice/finalize`
- `packages/vaaniq-voice/vaaniq/voice/pipeline/task.py` — replace lazy server imports with HTTP client calls
- `fly.toml` (new — Fly.io deploy config for voice server)

---

## Phase 4 — Outbound dial warm-up

**Status:** Not started  
**Effort:** 2 hrs  
**Latency saved:** ~1.5s TTFG for outbound calls (pipeline ready before person answers)

### Why this works for outbound only

Outbound call timeline:
```
POST /v1/voice/calls/outbound   → Twilio REST API call initiated
  ~9 seconds of ringing         ← opportunity window
Customer answers
  WebSocket connects            ← pipeline must be ready here
```

There are ~9 seconds between call initiation and WebSocket connect. The full pipeline cold start is ~1.5s. We can build the pipeline in background during the ring phase.

### Implementation

When the outbound call is initiated, immediately start a background task:

```python
# voice/router.py
@router.post("/v1/voice/calls/outbound")
async def initiate_outbound(req, background_tasks: BackgroundTasks):
    call_sid = await twilio_client.create_call(...)
    session = await create_session(...)

    # Start pipeline warm-up in background during ring phase
    background_tasks.add_task(
        warm_pipeline_for_session,
        session_id=session.id,
        context=context,
    )
    return {"session_id": session.id, "call_sid": call_sid}

async def warm_pipeline_for_session(session_id: str, context: VoiceCallContext):
    """Pre-build the pipeline and hold it ready. Called during ring phase."""
    warm_pipelines[session_id] = await build_pipeline(websocket=None, context=context)
```

When the WebSocket connects, check for a warm pipeline before building cold:

```python
# pipeline/task.py  
pipeline = warm_pipelines.pop(session_id, None)
if pipeline is None:
    pipeline, llm_context, transport, memory_saver = await build_pipeline(websocket, context)
```

Note: the Deepgram and Cartesia WebSocket connections are established inside `build_pipeline`. Pre-building them during ring phase means those ~1s connections are already open when the caller answers.

### Files

- `packages/vaaniq-server/vaaniq/server/voice/router.py` — add background warm-up task
- `packages/vaaniq-voice/vaaniq/voice/pipeline/task.py` — check `warm_pipelines` dict on connect
- `packages/vaaniq-voice/vaaniq/voice/pipeline/warm.py` (new) — `warm_pipelines` dict + helpers

---

## Phase 5 — "Deploy" button + cache invalidation

**Status:** Not started  
**Effort:** 1 hr  
**Effect:** UX correctness (callers get new agent version immediately after deploy, not after cache TTL)

### What

Currently there's a "Publish" action in the graph editor that saves `graph_config` to DB. After Phase 1 (graph cache), published changes won't take effect until the cache entry expires or the server restarts — callers during that window get the old version.

Fix: on publish, bump `graph_version` (Phase 1 migration) AND send a cache-invalidation signal to the voice server.

### Implementation

On agent publish in `agents/service.py`:
1. Increment `graph_version` (auto-invalidates cache key — new key = new compile)
2. Optionally: POST to voice server's internal API to pre-compile the new version immediately so the first post-deploy call isn't the one that pays compile cost

```python
# agents/service.py
async def publish(agent_id: str, graph_config: dict):
    await AgentRepository(db).increment_version(agent_id)
    # Optional: signal voice server to pre-warm new version
    await httpx.post(f"{VOICE_SERVER_URL}/internal/cache/warm/{agent_id}")
```

### Files

- `packages/vaaniq-server/vaaniq/server/agents/service.py` — bump version on publish
- `packages/vaaniq-voice-server/` — add `POST /internal/cache/warm/{agent_id}` endpoint

---

## Phase 6 — STT/TTS connection pooling (future sprint)

**Status:** Deferred  
**Effort:** 1 day  
**Latency saved:** ~900ms/call (eliminates per-call Deepgram WebSocket setup)

### What

Keep a pool of N idle WebSocket connections open to Deepgram and Cartesia. On call start, grab a connection from the pool instead of establishing a new one.

### Why deferred

Complex to implement correctly:
- Connections must be per-provider, per-sample-rate, per-language
- Need health checking, reconnection on drop, pool sizing
- Pipecat's STT/TTS services assume they own their connection — needs refactoring

Revisit when Phase 1–4 are live and production-proven.

---

## Latency Budget (target after all phases)

| Stage | Current | Target |
|---|---|---|
| Pipeline cold start | ~1,580ms | ~0ms (cached + pre-warmed) |
| Twilio → server network | ~50ms | ~20ms (Fly.io iad co-location) |
| VAD stop detection | ~350ms | ~350ms (unchanged — sweet spot) |
| Deepgram STT finalization | ~100ms | ~100ms |
| LangGraph (TTFT) | ~200–500ms | ~200–500ms (LLM-dependent) |
| Cartesia TTS first audio | ~80ms | ~80ms |
| **TTFG (outbound)** | **~1,580ms** | **~400ms** |
| **TTFG (inbound)** | **~1,580ms** | **~600ms** |
| **Turn latency (mid-call)** | **~600–900ms** | **~600–900ms** |
