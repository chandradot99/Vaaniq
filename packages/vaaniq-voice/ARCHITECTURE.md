# vaaniq-voice — Architecture

Voice pipeline package for Vaaniq. Handles PSTN phone calls via **Pipecat 0.0.101 + Twilio Media Streams**. Sits above `vaaniq-core` and `vaaniq-graph` in the dependency tree — the LangGraph agent is channel-agnostic; only the I/O layer differs per channel.

---

## Package Structure

```
packages/vaaniq-voice/
├── ARCHITECTURE.md                  ← you are here
├── pyproject.toml
├── tests/
└── vaaniq/voice/
    ├── __init__.py
    ├── constants.py                 # all magic numbers — sample rates, VAD params, timeouts
    ├── exceptions.py                # VoiceError, VoiceConfigError, ProviderNotFoundError, MissingAPIKeyError
    │
    ├── pipeline/
    │   ├── builder.py               # build_pipeline() — assembles Pipecat pipeline per call
    │   ├── task.py                  # run_voice_pipeline() — lifecycle, warm-up, finalization
    │   └── context.py               # VoiceCallContext dataclass — everything the pipeline needs
    │
    ├── services/
    │   ├── langgraph_service.py     # VaaniqLangGraphService — Pipecat FrameProcessor → LangGraph bridge
    │   ├── stt/
    │   │   ├── base.py              # create_stt_service() factory + registry
    │   │   ├── deepgram.py          # Deepgram Nova-3 (default)
    │   │   └── assemblyai.py        # AssemblyAI Universal-Streaming
    │   └── tts/
    │       ├── base.py              # create_tts_service() factory + registry
    │       ├── cartesia.py          # Cartesia Sonic-2 (default — lowest latency)
    │       ├── deepgram.py          # Deepgram TTS
    │       ├── elevenlabs.py        # ElevenLabs Flash v2.5 (voice cloning)
    │       └── azure.py             # Azure AI Speech (140+ locales)
    │
    └── transport/
        ├── base.py                  # create_transport() factory + registry
        └── twilio.py                # build_twilio_transport() — FastAPIWebsocketTransport + TwilioFrameSerializer
```

**Provider registry pattern** — all three provider axes (STT, TTS, transport) use the same factory:
```python
registry = {"deepgram": build_deepgram_stt, "assemblyai": build_assemblyai_stt}
return registry[provider](org_keys, ...)
```
Adding a provider = add a file, register in `base.py`. No changes to pipeline builder.

---

## How a Call Works (End-to-End)

### Inbound Call

```
1. Caller dials Twilio number
       → Twilio POST /webhooks/twilio/voice/inbound
       → verify X-Twilio-Signature
       → look up agent by phone number
       → create session row (channel="voice")
       → return TwiML <Stream url="wss://api.vaaniq.com/webhooks/twilio/voice/stream/{session_id}" />

2. Twilio opens WebSocket to /webhooks/twilio/voice/stream/{session_id}
       → accept WebSocket
       → read Twilio handshake (connected + start messages) → extract stream_sid
       → load session + agent + org_keys from DB
       → resolve STT/TTS providers from voice_config or org integrations
       → build Pipecat pipeline
       → queue initial LLMContextFrame → triggers turn-0 greeting
       → PipelineRunner.run() blocks until call ends

3. Call ends (caller hangs up or agent pushes EndFrame)
       → on_client_disconnected fires → queues EndFrame
       → pipeline drains → finalize_voice_session() saves transcript + execution events
       → Twilio POST /webhooks/twilio/voice/status (status=completed)
```

### Outbound Call

```
1. POST /v1/voice/calls/outbound  { agent_id, to_number, from_number, extra_context }
       → create session row (channel="voice", direction="outbound")
       → Twilio REST API: create call (url = /webhooks/twilio/voice/outbound?session_id=...)

2. Twilio dials customer (~9s ring phase)
       → customer answers
       → Twilio POST /webhooks/twilio/voice/outbound?session_id=...
       → return TwiML <Stream> (same as inbound)
       → same WebSocket pipeline flow from step 2 above
```

---

## Pipecat Pipeline

Each call gets **one isolated async task** — its own pipeline instance, its own LangGraph MemorySaver. No shared state between calls.

```
Transport.input()
    ↓  8kHz mu-law audio from Twilio WebSocket
DeepgramSTTService         — streaming transcription → TranscriptionFrame
    ↓
LLMUserAggregator          — buffers transcript until turn-end (TranscriptionUserTurnStopStrategy)
    ↓  LLMContextFrame (full user turn)
VaaniqLangGraphService     — LangGraph execution → LLMTextFrame (one per sentence)
    ↓
CartesiaTTSService         — streaming synthesis per sentence → AudioRawFrame
    ↓
LLMAssistantAggregator     — captures agent response back into context
    ↓
Transport.output()         — sends 8kHz mu-law audio back to Twilio
```

**Turn detection**: `TranscriptionUserTurnStopStrategy` — fires when Deepgram transcription arrives after VAD silence. Faster than pure VAD endpointing because it uses both the audio signal (VAD) and the transcript signal (Deepgram finalization).

**Interruptions**: Pipecat's `StartInterruptionFrame` / `StopInterruptionFrame` propagate instantly (SystemFrames bypass all queues). When user speaks over the agent, TTS stops mid-word and STT picks up the new utterance.

---

## VaaniqLangGraphService — The Bridge

`FrameProcessor` subclass that routes between the Pipecat frame world and LangGraph.

```
LLMContextFrame in
    → extract user text from context.messages
    → turn 0: ainvoke(initial_state)
    → turn N: ainvoke(Command(resume=user_text))
    → extract agent_text from final_state["messages"]
    → split into sentences (_split_sentences)
    → push one LLMTextFrame per sentence
LLMTextFrames out → TTS
```

**Key design choices:**

- **`ainvoke()` not `astream()`** — waits for full LangGraph response before sending to TTS. Sentence splitting creates the appearance of streaming (TTS starts on sentence 1 while LangGraph is "done"). True token-level streaming requires switching to `astream()` — future sprint.
- **Turn counter** — `self._turn` tracks call turn number. Passed to `TurnEventCollector` for execution tracing.
- **Callback injection** — `get_turn_callbacks(turn)` factory provides LangChain callbacks per turn. Used to wire `TurnEventCollector` into `ainvoke` config.
- **Session ended flag** — LangGraph sets `state["session_ended"] = True` when the agent decides to end. Service pushes `EndFrame` upstream and downstream to shut the pipeline down cleanly.

```python
# Sentence splitting for TTS pipelining
def _split_sentences(text: str) -> list[str]:
    # Split on . ! ? while preserving abbreviations
    # Each sentence goes to Cartesia as a separate request
    # Cartesia starts synthesizing sentence 1 while sentence 2 waits
```

---

## VoiceCallContext

Resolved once per call at WebSocket connect time. Passed into the pipeline builder — never mutated after creation.

```python
@dataclass
class VoiceCallContext:
    # Required (no defaults)
    session_id: str
    org_id: str
    agent_id: str
    agent_language: str          # e.g. "en-US", "hi-IN"
    graph_config: dict           # raw graph_config JSON from agents table
    initial_messages: list       # system prompt as OpenAI message format
    org_keys: dict               # Fernet-decrypted BYOK keys {provider: key}

    # Optional (with defaults)
    telephony_provider: str = "twilio"
    call_sid: str = ""
    stream_sid: str = ""
    from_number: str = ""
    to_number: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    stt_provider: str = "deepgram"
    stt_model: str | None = None      # None = provider default
    tts_provider: str = "cartesia"
    tts_model: str | None = None
    tts_speed: float | None = None
    agent_voice_id: str | None = None
    direction: str = "inbound"
    extra_context: dict = field(default_factory=dict)
```

**Resolution hierarchy** (in `context_builder.py`):
1. `phone_number.voice_config` — per-pipeline override (STT/TTS/language/voice)
2. Org BYOK integrations — auto-detect from what's configured
3. Platform defaults — Deepgram STT, Cartesia TTS

---

## Session Finalization

When a call ends, `finalize_voice_session()` runs under `asyncio.shield()` to survive FastAPI cancellation:

```
call ends
    → _shutdown_runner() pushes EndFrame, waits PIPELINE_SHUTDOWN_TIMEOUT_SECS (2s)
    → _finalize_session():
        asyncio.shield(finalize_voice_session(
            session_id, org_id, memory_saver, event_collectors
        ))
        → read messages from MemorySaver checkpoint
        → update sessions table: transcript, message_count
        → bulk insert SessionEvent rows from TurnEventCollectors
        → log voice_session_finalized {message_count, event_count}
```

`asyncio.shield()` is critical: FastAPI cancels the WebSocket handler coroutine when the connection closes. Without shield, the DB write is cancelled before it completes. Shield lets `finalize_voice_session` run to completion even as the parent is cancelled.

---

## Constants (constants.py)

All magic numbers in one place. Never scatter raw integers through pipeline code.

```python
TWILIO_SAMPLE_RATE          = 8_000     # Hz — hard PSTN constraint
VAD_CONFIDENCE              = 0.7       # Silero confidence threshold
VAD_START_SECS              = 0.2       # speech start sensitivity
VAD_STOP_SECS               = 0.35      # silence before turn-end fires
VAD_MIN_VOLUME              = 0.6       # ignore very quiet audio
PIPELINE_IDLE_TIMEOUT_SECS  = 10.0     # pipeline shuts down after 10s of no frames
PIPELINE_SHUTDOWN_TIMEOUT_SECS = 2.0   # wait this long for pipeline to drain on EndFrame
```

**Why VAD_STOP_SECS = 0.35 (not lower):**  
0.25 split "Okay. Thank you." into two separate turns — mid-thought pause triggered turn-end. 0.35 is the sweet spot: fast enough to feel responsive, doesn't split natural pauses.

---

## Audio Format

Twilio Media Streams sends **8kHz mono mu-law** — a hard PSTN constraint. Everything is configured at `sample_rate=8000`. Implications:

- Deepgram and AssemblyAI accept 8kHz input natively
- Cartesia and ElevenLabs handle 8kHz input; they synthesize at their native rate
- Speech-to-speech models (OpenAI Realtime, Gemini Live) lose their latency edge at 8kHz — not recommended for PSTN

---

## Latency Budget (current, production)

Measured end-to-end on first call (cold start):

| Stage | Measured | Notes |
|---|---|---|
| Silero VAD load | ~100ms | per-call today, will be pre-loaded (Plan Phase 2) |
| Pipeline build | ~400ms | includes graph compile, will be cached (Plan Phase 1) |
| Deepgram WS connect | ~900ms | biggest single cost, will be pooled (Plan Phase 6) |
| Cartesia WS connect | ~80ms | |
| **Cold start total** | **~1,580ms** | before turn 0 |
| VAD stop detection | ~350ms | stop_secs = 0.35 |
| Deepgram STT finalization | ~100ms | Nova-3 streaming |
| LangGraph (TTFT) | ~200–500ms | LLM-dependent |
| Cartesia first audio | ~80ms | |
| **Turn latency (mid-call)** | **~600–900ms** | after first turn |

After Plan Phases 1–4: cold start → ~0ms (cached + pre-warmed), TTFG outbound ~400ms.

---

## Execution Tracing

Every LangGraph turn's execution events are captured for the Execution tab in the UI.

```
get_turn_callbacks(turn: int) → [TurnEventCollector.as_callback_handler()]
    ↓ injected into ainvoke(config={"callbacks": [...]})
    ↓ LangChain fires on_chain_start / on_chain_end on every node
    ↓ TurnEventCollector accumulates SessionEvent objects
finalize_voice_session()
    ↓ collector.finalize() → list[SessionEvent]
    ↓ SessionEventRepository.bulk_insert(all_events)
```

---

## Planned Infrastructure Split (Plan Phase 3)

Currently the voice WebSocket runs inside `vaaniq-server` (Railway). Target:

```
vaaniq-voice-server  (Fly.io iad — near Twilio's US edge)
    • /webhooks/twilio/voice/*
    • Pipecat pipeline
    • Calls vaaniq-server for context and finalization over HTTP

vaaniq-server  (Railway)
    • All REST APIs
    • GET /internal/voice/context/{session_id}
    • POST /internal/voice/finalize
    • DB, auth, agents, sessions
```

Fly.io `iad` region is in Ashburn, VA — same geography as Twilio's US media edge. Eliminates 30–50ms of unnecessary network latency on every audio packet. Always-on 1vCPU/2GB: ~$12/month vs Railway's ~$87/month for always-on.

---

## What NOT To Do

- **Don't build a custom audio pipeline** — Pipecat handles VAD, interruptions, frame routing. Never roll your own.
- **Don't use `VAD_STOP_SECS < 0.35` without semantic endpointing** — 0.25 splits natural mid-sentence pauses into separate turns.
- **Don't compile the graph per turn** — `VaaniqLangGraphService` compiles once at call start. Per-turn compilation would add 50–200ms every turn.
- **Don't use `except Exception` to catch `asyncio.CancelledError`** — `CancelledError` is `BaseException`. FastAPI cancels WebSocket handlers on disconnect; always `asyncio.shield()` DB writes.
- **Don't use `asyncio.get_event_loop().create_task()`** — deprecated in Python 3.10+. Use `asyncio.create_task()`.
- **Don't trust Twilio webhooks without signature verification** — always validate `X-Twilio-Signature`.
- **Don't store Twilio auth token in code or env** — load from `org_keys` (BYOK, Fernet-encrypted) at call time.
- **Don't use speech-to-speech models for PSTN** — 8kHz constraint eliminates their latency advantage.

---

## Future: LiveKit WebRTC (Sprint 5)

For browser-based voice (no phone required):

- Transport: `LiveKit` instead of `FastAPIWebsocketTransport`
- Audio: up to 48kHz wideband (vs 8kHz PSTN) — better STT accuracy, better TTS quality
- Latency: 50–150ms (vs 300–500ms PSTN) — built-in AEC, jitter buffers
- Same `VaaniqLangGraphService` — zero changes to agent logic
- Same STT/TTS provider factories — same providers work over WebRTC

The package is designed so PSTN and WebRTC share all business logic; only the transport layer differs.

---

*Last updated: 2026-04-08*
