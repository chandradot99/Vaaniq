# Naaviq — Architecture Decisions & Roadmap

Permanent record of key architectural decisions and what is deliberately deferred to v1.5 / v2.
Update this file when decisions change — do not open new debates on closed items.

---

## Visual Builder: Code Generation vs JSON Runtime

**Decision: JSON config → LangGraph at runtime. No code generation.**

The visual builder stores agent behaviour as JSON in `agents.graph_config`. At session time, `GraphBuilder.build()` converts that JSON into a LangGraph `CompiledStateGraph`. Writing Python by hand and dragging nodes in the UI produce the same graph.

```
User drags nodes → JSON in DB → GraphBuilder → LangGraph (runtime)
```

| Python (hand-written) | Our JSON config |
|---|---|
| `create_agent(model=..., tools=[...])` | `{ type: "llm_response", config: { tools: [...] } }` |
| `HumanInTheLoopMiddleware(interrupt_on={...})` | `{ type: "human_review", config: { ... } }` |
| `checkpointer=InMemorySaver()` | Injected by `chat/service.py` as `AsyncPostgresSaver` |

**Code export** (download the generated Python) — natural premium feature for v2, deferred.

---

## Middleware: Visible Node, Not Hidden Layer

**Decision: Middleware concepts are exposed as graph nodes, not hidden infrastructure.**

`HumanInTheLoopMiddleware` exists in LangChain but it is a code-level abstraction. For a visual builder, the equivalent is a `human_review` node that users can see and position in their graph.

Benefits: visible, auditable, positionable, conditionally wirable.

Other middleware (rate limiting, cost guardrails, content filtering): implement at FastAPI middleware level, not as graph nodes. Not in v1.

---

## Context Window Management

**Decision: 3-tier approach. Only Tier 1 in v1.**

Why not mid-conversation compaction: LangGraph Platform pauses graph execution between steps to summarize, adding 2–5s latency. This is unacceptable for voice agents and poor UX for chat. Most real agent conversations (10–50 turns) are 5k–20k tokens — well under GPT-4o's 128k / Claude's 200k limit.

### Tier 1 — v1 (implemented)

In `llm_response.py`, before every LLM call:
```python
from langchain_core.messages import trim_messages
messages = trim_messages(state["messages"], max_tokens=50_000, strategy="last")
```
Silent, zero latency, conversation never pauses. The 50k limit is a safety guard that rarely fires.

### Tier 2 — v1.5 (between sessions, async)

After a session ends, run an async summarizer that:
1. Calls the LLM with the full transcript
2. Stores the compressed summary in `sessions.summary`
3. Next session for the same user gets `"Previous context: {summary}"` prepended to the system prompt

`state["summary"]` in `SessionState` is reserved for this. This is how Vapi/Retell handle long-running customer relationships.

### Tier 3 — v2 (LangGraph Platform)

For extremely long sessions (2h+ calls, multi-day support threads), LangGraph Platform handles compaction natively. No custom code — defer entirely.

---

## MCP (Model Context Protocol)

**Decision: Defer to v1.5.**

MCP is real via `langchain-mcp-adapters`. It would let our `TOOL_REGISTRY` connect to any MCP server (filesystem, databases, Slack, GitHub, etc.) — a significant capability expansion.

Why deferred: adds complexity around security, sandboxing, and MCP server lifecycle management. Current Google tools + HTTP request node cover immediate v1 use cases. Revisit when the tool ecosystem is mature.

Implementation when ready:
- `MCPToolset` wraps an MCP server; tools surface in our registry as regular tools
- UI: new "MCP Server" integration type in the Integrations page
- Security: MCP servers run in isolated subprocesses or remote-hosted; never trust arbitrary MCP payloads

---

## Skills / Agent Templates

**Decision: Defer to v2.**

Skills are pre-built agent templates (e.g., "Customer Support Agent", "Appointment Booking Agent") — essentially pre-populated `graph_config` JSON. Pure UI feature, no backend changes.

Why deferred: template quality depends on the builder being great first. Build the foundation, then populate it with validated, tested templates.

---

## Multi-Agent (Agent-Calling-Agent)

**Decision: Defer to v2.**

LangGraph supports agents as subgraphs that other agents can invoke. Use cases: an orchestrator agent delegates to specialist agents (calendar agent, email agent, CRM agent).

Why deferred: adds significant graph complexity, debugging is harder, and most v1 use cases are single-agent. Revisit when customers explicitly need it.

---

## Channel Architecture

The LangGraph is **channel-agnostic**. Only the I/O layer differs:

```
Voice (PSTN):    Audio → Pipecat STT  → text → LangGraph → text → Pipecat TTS → Audio
Voice (WebRTC):  Audio → LiveKit STT  → text → LangGraph → text → LiveKit TTS → Audio
Chat:            Text  → SSE          → text → LangGraph → text → SSE stream  → UI
WhatsApp:        Text  → webhook      → text → LangGraph → text → WhatsApp API → user
```

Voice channels: Pipecat (PSTN/Twilio) and LiveKit (WebRTC) are the only supported pipelines — never build a custom VAD/interruption/audio pipeline.

---

## Persistent Memory (Checkpointing)

**Decision: `AsyncPostgresSaver` from `langgraph-checkpoint-postgres`.**

- Thread ID format: `"{org_id}:{session_id}"` — org-prefixed for multi-tenant isolation
- `InMemorySaver` is only acceptable for unit tests — never in production
- `await checkpointer.setup()` called once at server startup via FastAPI lifespan
- Uses `psycopg` (not `asyncpg`) — required by `langgraph-checkpoint-postgres`

---

## Sessions Table

**Decision: Single generic `sessions` table with `channel` column.**

All channels (voice, chat, WhatsApp, SMS) share one table. `channel` discriminates the type. Adding a new channel never requires a new table or migration — just a new `channel` value.

---

## Streaming

**Decision: SSE (Server-Sent Events) for chat streaming.**

- Backend: `StreamingResponse(text/event-stream)` using `graph.astream(stream_mode=["updates","messages"])`
- Frontend: `fetch()` + `ReadableStream` reader (not `EventSource` — we need POST + auth headers)
- Event types: `token`, `node_start`, `node_end`, `human_review`, `ended`
- WebSocket is not used for chat — SSE is simpler for unidirectional streaming and works through all proxies

---

## Graph Layout

**Decision: Left-to-right.**

React Flow `Position.Left` for target handles, `Position.Right` for source handles. Industry standard for pipeline/workflow builders (n8n, Langflow, Flowise all use left-to-right). Default node x-positions: `index * 280`, y: `200`.

---

*Last updated: 2026-04-03*
