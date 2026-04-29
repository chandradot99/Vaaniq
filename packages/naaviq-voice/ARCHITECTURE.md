# naaviq-voice — Architecture

Voice pipeline package for Naaviq. Handles phone calls and browser WebRTC via **LiveKit Agents SDK**. Sits above `naaviq-core` and `naaviq-graph` in the dependency tree — the LangGraph agent is channel-agnostic; only the I/O layer differs per channel.

---

## Package Structure

```
packages/naaviq-voice/
├── ARCHITECTURE.md                  ← you are here
├── pyproject.toml
├── tests/
└── naaviq/voice/
    ├── __init__.py
    ├── exceptions.py                # VoiceError, VoiceConfigError, ProviderNotFoundError
    │
    ├── pipeline/
    │   └── context.py               # VoiceCallContext dataclass — everything the agent needs
    │
    ├── agent.py                     # run_voice_agent() — LiveKit AgentSession lifecycle
    ├── worker.py                    # LiveKit WorkerOptions + entrypoint dispatch
    │
    ├── llm/
    │   ├── __init__.py
    │   └── langgraph.py             # LangGraphLLM + LangGraphLLMStream — LiveKit LLM adapter
    │
    ├── stt/
    │   ├── __init__.py              # create_stt_plugin() factory
    │   └── sarvam.py                # Custom LiveKit STT plugin for Sarvam AI (Indian languages)
    │
    └── tts/
        ├── __init__.py              # create_tts_plugin() factory
        └── sarvam.py                # Custom LiveKit TTS plugin for Sarvam AI
```

---

## How a Call Works (End-to-End)

### Inbound Call (Twilio → LiveKit SIP → Agent)

```
1. Caller dials Twilio number
       → Twilio POST /webhooks/twilio/voice/inbound  (naaviq-voice-server)
       → verify Twilio signature
       → look up agent by phone number
       → create session row (channel="voice", direction="inbound")
       → create LiveKit room (name=session_id, metadata={"session_id": session_id})
       → return TwiML: <Dial><Sip>sip:{session_id}@{livekit-sip-domain}</Sip></Dial>

2. Twilio connects to LiveKit SIP
       → LiveKit SIP dispatch rule receives the call
       → creates a room, dispatches job to naaviq-voice worker

3. Worker entrypoint fires
       → reads session_id from room metadata
       → if metadata empty (dispatch-rule-created room): resolve by phone number from room name
       → loads VoiceCallContext from DB (agent config, org keys, STT/TTS config)
       → loads/compiles LangGraph from in-process cache
       → calls run_voice_agent() — blocks until call ends

4. Agent runs
       → session.start() connects to LiveKit room
       → first agent_state_changed("listening") → session.generate_reply() (turn 0 greeting)
       → user speaks → LiveKit VAD + STT → LangGraphLLM.chat() → TTS → speaker
       → repeat until session_ended=True in LangGraph state

5. Call ends
       → _on_session_ended(): finalize_voice_session() → DB write
       → delete LiveKit room (disconnects all participants including browser)
       → safety-net finalization runs (no-op if already finalized)
```

### Outbound Call — LiveKit Native (production)

```
1. POST /v1/voice/calls/outbound  { agent_id, from_number, to_number }  (naaviq-server)
       → create session row (direction="outbound")
       → create LiveKit room (name=session_id, metadata={"session_id": session_id})
       → CreateAgentDispatch → worker joins room immediately (reads metadata correctly)
       → CreateSIPParticipant → LiveKit calls user's phone via outbound SIP trunk

2. User answers
       → connected to the pre-created session_id room
       → agent greets them (turn 0 already dispatched)

Requires: LIVEKIT_OUTBOUND_SIP_TRUNK_ID set in env.
```

### Outbound Call — Twilio Fallback (no outbound SIP trunk)

```
1. POST /v1/voice/calls/outbound
       → create session row (direction="outbound")
       → Twilio REST API: create call (twiml_url = /webhooks/twilio/voice/outbound?session_id=...)

2. User answers
       → Twilio POST /webhooks/twilio/voice/outbound?session_id=...
       → create LiveKit room + return TwiML SIP dial
       → Twilio connects to LiveKit SIP → dispatch rule creates room with phone-number name
       → worker resolves session via _find_session_by_phone() fallback

Note: Twilio rewrites SIP headers (replaces session_id username with its own phone number),
so room metadata is empty and session lookup falls back to phone + status=active query.
The LiveKit-native path (above) avoids this entirely.
```

---

## LiveKit Agent Pipeline

Each call runs as an isolated LiveKit `AgentSession` — its own VAD, STT stream, LLM turns, TTS synthesis. No shared state between concurrent calls.

```
LiveKit room (WebRTC / SIP)
    ↓  audio from caller
Silero VAD              — detects speech start/end
    ↓
STT plugin              — streaming transcription (Deepgram / Sarvam / AssemblyAI)
    ↓  transcript text
LangGraphLLM.chat()     — runs one LangGraph turn, streams tokens
    ↓  text chunks
TTS plugin              — synthesizes speech chunk by chunk (ElevenLabs / Cartesia / Azure / Sarvam)
    ↓  audio
LiveKit room            — plays audio to caller
```

**Turn detection**: STT-based endpointing (`min_endpointing_delay`). LiveKit waits for the STT to signal end-of-utterance before routing to LLM. No manual VAD parameter tuning needed.

**Interruptions**: `allow_interruptions=True` on the Agent. When the user speaks while the agent is talking, LiveKit stops TTS mid-sentence and routes the new input to STT immediately.

**Endpointing delays by provider:**
- Deepgram / ElevenLabs / Cartesia / Azure: `300ms` (default)
- Sarvam AI: `70ms` (Sarvam signals faster, 300ms causes cut-off)

---

## LangGraphLLM — The Bridge

`livekit.agents.llm.LLM` subclass that routes between LiveKit's turn model and LangGraph.

```python
class LangGraphLLM(llm.LLM):
    def chat(self, chat_ctx, ...) -> LangGraphLLMStream:
        # Returns a stream for this turn
        # turn 0 → greeting (no user input)
        # turn N → Command(resume=user_text)
```

```python
class LangGraphLLMStream(llm.LLMStream):
    async def _run(self) -> None:
        if self._turn == 0:
            # Emit greeting from graph_config start node (no LLM call)
            # Advance graph through start → inbound_message interrupt
            ...

        else:
            # graph.astream_events(Command(resume=user_text), version="v2")
            # Filter: skip on_chat_model_stream from internal nodes
            #         (condition, collect_data, human_review — not spoken to user)
            # Push ChatChunk objects as tokens arrive → TTS starts on first chunk
            # After loop: aget_state() → check session_ended
            # If session_ended → asyncio.create_task(on_session_ended())
```

**Key design choices:**

- **`astream_events()` v2** — token streaming. TTS starts on the first token instead of waiting for the full LangGraph response. Reduces perceived latency by ~200–400ms.
- **Internal node filtering** — `condition`, `collect_data`, `human_review` nodes use LLMs for routing/extraction. Their tokens are filtered by node ID so they never reach TTS.
- **Non-streaming fallback** — when no tokens are emitted (end_session farewell, collect_data re-ask), `_extract_interrupt_text()` / `_extract_agent_text()` pulls the text from the final graph state and emits it as a single chunk.
- **`session_ended` via `aget_state()`** — always reads the final state after the event loop rather than trying to detect it from `on_chain_end` events. `on_chain_end` output format is unreliable when streaming nodes run before end_session.

---

## VoiceCallContext

Resolved once per call in `_load_context()`. Passed into `run_voice_agent()` — never mutated after creation.

```python
@dataclass
class VoiceCallContext:
    # Identity
    session_id: str
    org_id: str
    agent_id: str

    # Agent config
    agent_language: str           # e.g. "en-US", "hi-IN"
    graph_config: dict            # raw graph_config JSON from agents table
    graph_version: int
    initial_messages: list        # system prompt as message dicts
    org_keys: dict                # Fernet-decrypted BYOK keys {provider: key}

    # STT / TTS
    stt_provider: str = "deepgram"
    stt_model: str | None = None
    tts_provider: str = "elevenlabs"
    tts_model: str | None = None
    tts_speed: float | None = None
    tts_voice_id: str | None = None

    # Call metadata
    call_sid: str = ""
    from_number: str = ""
    to_number: str = ""
    direction: str = "inbound"
    extra_context: dict = field(default_factory=dict)
```

**Resolution hierarchy** (in `context_builder.py`):
1. `phone_number.voice_config` — per-pipeline override (STT/TTS/language/voice)
2. Org BYOK integrations — auto-detect from what's configured
3. Platform defaults — Deepgram STT, ElevenLabs TTS

---

## STT / TTS Factories

```python
# stt/__init__.py
def create_stt_plugin(context: VoiceCallContext) -> STT:
    match context.stt_provider:
        case "deepgram":   return deepgram.STT(model=..., language=...)
        case "sarvam":     return SarvamSTT(api_key=..., language=...)
        case "assemblyai": return assemblyai.STT(...)
        case "azure":      return azure.STT(...)

# tts/__init__.py
def create_tts_plugin(context: VoiceCallContext) -> TTS:
    match context.tts_provider:
        case "elevenlabs": return elevenlabs.TTS(voice=..., model=...)
        case "cartesia":   return cartesia.TTS(voice=..., model=...)
        case "azure":      return azure.TTS(voice=...)
        case "deepgram":   return deepgram.TTS(model=...)
        case "sarvam":     return SarvamTTS(api_key=..., voice=...)
```

Adding a provider: add a file in `stt/` or `tts/`, add a case in the factory. No changes to `agent.py` or `worker.py`.

---

## Session Lifecycle & Finalization

```
call ends (user hangs up or end_session node fires)
    │
    ├─ Normal path (end_session node):
    │     LangGraphLLMStream detects session_ended=True
    │     → asyncio.create_task(_trigger_session_end())
    │     → waits for farewell speech to finish (agent_state_changed event)
    │     → calls _on_session_ended():
    │           finalize_voice_session()   ← DB write while room is still open
    │           delete LiveKit room        ← disconnects all participants
    │
    └─ Safety-net path (user hung up mid-call):
          run_voice_agent() returns
          → safety-net finalize_voice_session() called
          → no-op if already finalized (session.transcript is set)
          → delete LiveKit room (404 if already deleted — suppressed)
```

**Why finalize before room deletion:**
LiveKit cancels the worker entrypoint task with "did not exit in time" if the room is deleted while a DB write is still in flight. Finalizing first (while room is open) prevents this race.

**Execution tracing:**
Each user turn fires `_on_turn_events(turn, raw_events)` with all `astream_events` output. `TurnEventCollector` ingests these and produces `SessionEvent` rows bulk-inserted into `session_events` (populates the Executions tab in the Sessions UI).

---

## Worker — Session Resolution

The worker reads `session_id` from the LiveKit room metadata. Room metadata is set when **we** pre-create the room (inbound webhook and LiveKit-native outbound). When the SIP dispatch rule creates the room (Twilio fallback outbound path), metadata is empty.

**Important:** use `ctx.job.room.metadata` (the Room proto from the dispatched job, populated at dispatch time), NOT `ctx.room.metadata` (the WebRTC Room object, which is only populated after `ctx.connect()` is called).

```python
# Priority order in entrypoint():
session_id = (
    ctx.job.room.metadata["session_id"]  # 1. pre-created room (ideal)
    or _find_session_by_phone(phone)     # 2. phone lookup from room name
)

# _find_session_by_phone():
# Room name from dispatch rule: "+17407576101_RandomSuffix"
# phone = "+17407576101" (Twilio caller number)
# Query: session WHERE (user_id=phone OR meta->>'from'=phone)
#          AND channel='voice' AND status='active'
#          AND created_at > now()-5min
#        ORDER BY created_at DESC LIMIT 1
```

---

## Latency Budget

| Stage | Typical | Notes |
|---|---|---|
| LiveKit worker startup | 0ms | worker stays connected, pre-warmed |
| Graph cache hit | ~2ms | compiled once per agent version, cached in-process |
| Checkpointer (Postgres) | ~5ms | AsyncPostgresSaver |
| STT (Deepgram) connection | ~50ms | persistent WebSocket, reused per call |
| LangGraph TTFT | ~200–600ms | LLM-dependent (GPT-4o ~200ms, Claude ~400ms) |
| TTS first audio chunk | ~80–150ms | Cartesia ~80ms, ElevenLabs ~150ms |
| **Mid-call turn latency** | **~400–800ms** | after greeting |

**Sarvam AI (Indian languages):** STT endpointing at 70ms (vs 300ms) — significantly faster perceived response for Hindi/Hinglish.

---

## Indian Language Support

Sarvam AI supports 11 Indian languages including Hindi, Hinglish, Tamil, Telugu, Marathi. Set `stt_provider=sarvam` and `tts_provider=sarvam` on the phone number's voice config.

The Sarvam STT and TTS plugins (`stt/sarvam.py`, `tts/sarvam.py`) implement LiveKit's `STT` and `TTS` abstract base classes using Sarvam's HTTP API. Endpointing delay is automatically set to 70ms when Sarvam STT is active.

---

## What NOT To Do

- **Don't use Pipecat** — the pipeline was fully migrated to LiveKit Agents. Pipecat is no longer a dependency.
- **Don't build a custom VAD/interruption handler** — LiveKit + Silero handle this. `allow_interruptions=True` on `Agent` is all that's needed.
- **Don't compile the graph per turn** — `get_or_compile()` caches compiled graphs per `(agent_id, graph_version)`. Per-turn compilation adds 50–200ms every turn.
- **Don't filter LLM tokens by content** — filter by `node_id` (pre-computed internal node IDs from `graph_config`). Content-based filtering is fragile.
- **Don't use `session.transcript` to check active status** — transcript defaults to `[]` (empty list), not `NULL`. Use `session.status == "active"` instead.
- **Don't finalize after room deletion** — LiveKit cancels the entrypoint task when the room closes. Always finalize while the room is still open.
- **Don't trust the room name as session_id** — the SIP dispatch rule names rooms after the Twilio caller number, not the session UUID. Always read from room metadata first.
- **Don't read `ctx.room.metadata` in the entrypoint** — `ctx.room` is the WebRTC Room object; its metadata is only populated after `ctx.connect()`. Read `ctx.job.room.metadata` instead (the Room proto from the dispatched job, available immediately).
- **Don't set `VAD_STOP_SECS` manually** — LiveKit's STT-based endpointing replaces VAD-parameter tuning. Adjust `min_endpointing_delay` on `Agent` instead (default 300ms, 70ms for Sarvam).
- **Don't use `asyncio.get_event_loop().create_task()`** — deprecated in Python 3.10+. Use `asyncio.create_task()`.

---

*Last updated: 2026-04-12*
