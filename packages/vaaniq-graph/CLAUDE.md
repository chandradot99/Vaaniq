# vaaniq-graph — Architecture Reference

> This file documents the graph engine design. Read it at the start of every session touching this package.

---

## What This Package Does

`vaaniq-graph` is the execution engine that turns a visual agent graph (stored as JSON) into a running LangGraph. It has no dependency on `vaaniq-server` — it is a standalone Python package that any FastAPI app can use.

```
graph_config JSON  →  GraphBuilder.build()  →  Compiled LangGraph  →  execute
```

---

## The Three-Layer Model

```
UI Layer       React Flow canvas  →  toObject()  →  graph_config JSON
               (position, node type, config panel values)

Storage Layer  graph_config JSONB column in agents table (vaaniq-server)
               Python ignores position — used only by React Flow

Runtime Layer  GraphBuilder reads JSON → builds real LangGraph → executes
               NODE_REGISTRY maps type strings → handler classes
               Tools resolved from TOOL_REGISTRY (vaaniq-tools)
               Checkpointer = PostgresSaver (thread_id = session_id)
```

The JSON is the single source of truth. React Flow renders it. Python executes it. They are the same graph in two representations.

---

## graph_config JSON Schema

```json
{
  "entry_point": "greet",
  "guards": [],
  "nodes": [
    {
      "id": "greet",
      "type": "llm_response",
      "position": { "x": 100, "y": 100 },
      "config": {
        "instructions": "Greet the caller and ask how you can help.",
        "tools": [],
        "rag_enabled": false
      }
    },
    {
      "id": "route",
      "type": "condition",
      "position": { "x": 300, "y": 100 },
      "config": {
        "router_prompt": "What does the user want?",
        "routes": [
          { "label": "booking",  "description": "User wants to book an appointment" },
          { "label": "pricing",  "description": "User is asking about pricing" },
          { "label": "other",    "description": "Anything else" }
        ]
      }
    },
    {
      "id": "collect_booking",
      "type": "collect_data",
      "position": { "x": 500, "y": 50 },
      "config": {
        "fields": [
          { "name": "name", "type": "string", "prompt": "May I have your name?",    "required": true },
          { "name": "date", "type": "date",   "prompt": "What date works for you?", "required": true }
        ]
      }
    },
    {
      "id": "book_slot",
      "type": "run_tool",
      "position": { "x": 700, "y": 50 },
      "config": {
        "tool": "google_calendar_create",
        "input": {
          "title": "Meeting with {{collected.name}}",
          "date":  "{{collected.date}}"
        }
      }
    },
    {
      "id": "notify",
      "type": "http_request",
      "position": { "x": 700, "y": 200 },
      "config": {
        "method": "POST",
        "url": "https://hooks.your-app.com/booking-confirmed",
        "headers": { "Authorization": "Bearer {{org_keys.webhook_secret}}" },
        "body": { "name": "{{collected.name}}", "date": "{{collected.date}}" },
        "save_response_to": "webhook_result",
        "timeout_seconds": 10
      }
    },
    {
      "id": "end",
      "type": "end_session",
      "position": { "x": 900, "y": 100 },
      "config": {
        "farewell_message": "All done! We'll see you then."
      }
    }
  ],
  "edges": [
    { "id": "e1", "source": "greet",           "target": "route" },
    { "id": "e2", "source": "route",           "target": "collect_booking", "condition": "booking" },
    { "id": "e3", "source": "route",           "target": "end",             "condition": "pricing" },
    { "id": "e4", "source": "route",           "target": "end",             "condition": "other" },
    { "id": "e5", "source": "collect_booking", "target": "book_slot" },
    { "id": "e6", "source": "book_slot",       "target": "end" }
  ]
}
```

**Rules:**
- `position` is ignored at runtime — React Flow only
- Edges with `condition` key are conditional; edges without are direct
- All conditional edges from the same source node must have a `condition` node as their source
- `entry_point` must match the `id` of a node in `nodes`
- `guards` is a top-level array (not inside `nodes`) — see Guard Nodes section

---

## Node Types

Full palette exposed in the visual UI. Every `type` string maps to a class in `NODE_REGISTRY`.

### Input
| Type | What it does | Key config fields |
|---|---|---|
| `start` | Entry point — triggered when session begins | _(none)_ |
| `inbound_message` | Triggered on each user turn (chat/WhatsApp) | _(none)_ |

### Logic
| Type | What it does | Key config fields |
|---|---|---|
| `llm_response` | Agent speaks using LLM; optionally calls tools | `instructions`, `tools[]`, `rag_enabled`, `voice_id` |
| `condition` | LLM-based routing — sets `state["route"]` | `router_prompt`, `routes[{label, description}]` |
| `collect_data` | Gather structured fields from user over multiple turns | `fields[{name, type, prompt, required}]` |
| `set_variable` | Set a state field directly without LLM | `key` (dot-path into state), `value` (literal or `{{template}}`) |

### Action
| Type | What it does | Key config fields |
|---|---|---|
| `run_tool` | Call a pre-built tool directly (no LLM decision) | `tool`, `input{field: "{{var}}"}` |
| `http_request` | Call any external REST API or webhook | `method`, `url`, `headers`, `body`, `save_response_to`, `timeout_seconds` |
| `send_message` | Proactively push a message mid-flow (WhatsApp/SMS) | `channel`, `to`, `template`, `body` |
| `transfer_human` | Hand off to a real agent | `transfer_number`, `whisper_template` |
| `end_session` | End gracefully | `farewell_message` |
| `post_session_action` | Side effects after session ends — runs as Celery task | `actions[]` |

### Data
| Type | What it does | Key config fields |
|---|---|---|
| `rag_search` | Search knowledge base, write to `state["rag_context"]` | `top_k`, `min_score` |

### Flow
| Type | What it does | Key config fields |
|---|---|---|
| `parallel` | Run multiple branches simultaneously, wait for all | `branches[{id, entry_node}]` |
| `subgraph` | Embed another agent's graph — reusable flows | `agent_id` |
| `delay` | Pause execution for N seconds or until an external event | `seconds` or `event_key` |

### Safety
| Type | What it does | Key config fields |
|---|---|---|
| `guard` | Global override checked every turn (lives in `guards[]`, not `nodes[]`) | `condition_prompt`, `action`, `target_node` |

---

## Custom Tools — Three-Tier Model

Not everything a user needs is in the pre-built tool library. We handle this in three tiers:

### Tier 1 — Pre-built tools (~70% of use cases)
Registered in `TOOL_REGISTRY` in `vaaniq-tools`. Google Calendar, Gmail, HubSpot, Razorpay, Freshdesk, etc. User picks from a list in the `llm_response` or `run_tool` node config. Their API key (BYOK) is injected automatically.

### Tier 2 — HTTP Request node (~25% of use cases)
A generic `http_request` node that makes any REST API call. User configures URL, method, headers, body — all support `{{template}}` syntax. Response is saved to a named state key.

**This is the recommended escape hatch for:**
- Proprietary or internal APIs
- Webhooks to n8n / Zapier / Make for complex logic
- Any API we haven't built a pre-built tool for yet

No security concerns — we make one HTTP call to a URL the user provides. The user owns the endpoint and can write any logic there in any language.

```json
{
  "type": "http_request",
  "config": {
    "method": "POST",
    "url": "https://api.internal.com/check-stock",
    "headers": { "X-API-Key": "{{org_keys.internal_key}}" },
    "body": { "sku": "{{collected.product_sku}}" },
    "save_response_to": "stock_result",
    "timeout_seconds": 10
  }
}
```

### Tier 3 — Code node (v2, not yet implemented)
Inline Python via Monaco editor in the UI. Runs in a `RestrictedPython` sandbox for pure transformation logic (no arbitrary imports, no I/O). Covers data parsing, calculations, string manipulation that don't warrant a full HTTP endpoint.

**Do not implement in v1.** HTTP Request node covers everything for now.

---

## Node Pattern

All nodes are **classes** — config and org_keys are injected at build time, not call time. Never use module-level globals for per-org state.

```python
# vaaniq/graph/nodes/base.py
class BaseNode:
    def __init__(self, config: dict, org_keys: dict):
        self.config = config
        self.org_keys = org_keys  # decrypted BYOK keys for this org

    async def __call__(self, state: SessionState) -> SessionState:
        raise NotImplementedError
```

```python
# vaaniq/graph/nodes/llm_response.py
class LLMResponseNode(BaseNode):
    async def __call__(self, state: SessionState) -> SessionState:
        tool_fns = [TOOL_REGISTRY[t](self.org_keys) for t in self.config["tools"]]
        llm = ChatOpenAI(api_key=self.org_keys["openai"]).bind_tools(tool_fns)
        # ... invoke, update state, return
        return {**state, "messages": updated_messages}
```

```python
# vaaniq/graph/nodes/http_request.py
class HttpRequestNode(BaseNode):
    async def __call__(self, state: SessionState) -> SessionState:
        resolved = TemplateResolver.resolve(self.config, state, self.org_keys)
        async with httpx.AsyncClient(timeout=resolved["timeout_seconds"]) as client:
            resp = await client.request(
                method=resolved["method"],
                url=resolved["url"],
                headers=resolved.get("headers", {}),
                json=resolved.get("body"),
            )
            resp.raise_for_status()
        save_key = self.config.get("save_response_to")
        if save_key:
            return {**state, save_key: resp.json()}
        return state
```

**Never mutate state — always return `{**state, "field": new_value}`.**

**Adding a new node type:**
1. Create `vaaniq/graph/nodes/<type>.py` with a class extending `BaseNode`
2. Register it in `NODE_REGISTRY` in `vaaniq/graph/nodes/__init__.py`
3. Add the React Flow node component in the frontend

---

## GraphBuilder

```python
# vaaniq/graph/builder.py
class GraphBuilder:
    def build(self, graph_config: dict, org_keys: dict) -> CompiledGraph:
        workflow = StateGraph(SessionState)

        for node in graph_config["nodes"]:
            handler = NODE_REGISTRY[node["type"]](
                config=node["config"],
                org_keys=org_keys,
            )
            workflow.add_node(node["id"], handler)

        # Group conditional edges by source
        conditional: dict[str, list] = defaultdict(list)
        for edge in graph_config["edges"]:
            if "condition" in edge:
                conditional[edge["source"]].append(edge)
            else:
                target = edge["target"] if edge["target"] != "end" else END
                workflow.add_edge(edge["source"], target)

        for source, edges in conditional.items():
            mapping = {e["condition"]: e["target"] for e in edges}
            workflow.add_conditional_edges(
                source,
                lambda s: s["route"],   # condition node writes state["route"]
                mapping,
            )

        workflow.add_edge(START, graph_config["entry_point"])  # preferred over set_entry_point()

        # Use AsyncPostgresSaver — our stack is fully async
        # Call checkpointer.setup() once at startup to create its tables
        return workflow.compile(checkpointer=checkpointer)
```

---

## Memory — Multi-Turn Conversations

LangGraph's `PostgresSaver` checkpointer handles all conversation memory automatically. Every node execution saves state to PostgreSQL, keyed by `thread_id`.

```
session_id  →  thread_id  →  checkpointer key
```

On each new user message, the graph resumes from the saved state — `state["collected"]`, `state["messages"]`, current node, everything intact. No custom session storage needed.

**Development:** use `InMemorySaver`
**Production:** use `PostgresSaver` (same PostgreSQL instance)

---

## Tools — BYOK Integration

Tools are registered in `TOOL_REGISTRY` (in `vaaniq-tools`). When an `llm_response` node has `"tools": ["google_calendar_create", "crm_create_lead"]`:

1. `GraphBuilder` passes `org_keys` (decrypted Fernet keys) into the node at build time
2. Node resolves tools from registry: `TOOL_REGISTRY[name](org_keys)`
3. Tools receive the org's own API key — never a hardcoded platform key
4. LLM decides when to call tools via `bind_tools()`; `ToolNode` executes them

---

## Template Variable Syntax

Used in `run_tool`, `http_request`, `set_variable`, and `send_message` configs to inject runtime state values. Resolved by `TemplateResolver` before the node executes.

```
{{collected.name}}        →  state["collected"]["name"]
{{collected.date}}        →  state["collected"]["date"]
{{user.id}}               →  state["user_id"]
{{crm.email}}             →  state["crm_record"]["email"]
{{channel}}               →  "voice" | "chat" | "whatsapp"
{{org_keys.webhook_key}}  →  org_keys["webhook_key"]  (for http_request headers/auth)
{{webhook_result.id}}     →  state["webhook_result"]["id"]  (from previous http_request)
```

---

## Guard Nodes — Global Overrides

Guards are defined at the top level of `graph_config` (not inside `nodes`). They form a preamble subgraph compiled ahead of the main graph and run on every turn before the main graph resumes.

```
Every turn:
  → run guards in order (anger detection, profanity, off-topic, etc.)
  → first match wins: jump to configured target_node
  → if none match: enter main graph at current node
```

```json
{
  "guards": [
    {
      "condition_prompt": "Is the user expressing anger or serious frustration?",
      "action": "jump",
      "target_node": "transfer_human"
    },
    {
      "condition_prompt": "Is the user asking to speak to a human?",
      "action": "jump",
      "target_node": "transfer_human"
    }
  ]
}
```

---

## Simple Mode

`simple_mode: true` on the agent means the user only fills in a system prompt + selects tools. The backend auto-generates a minimal `graph_config`:

```
Start → LLM Response (with user's system prompt + tools) → End
```

Same `GraphBuilder`, same runtime. Simple mode is just a convenience shorthand that skips the visual canvas. Useful for onboarding and non-technical users.

---

## Streaming

LangGraph's own streaming API (not LangChain's `astream_events`). Use `version="v2"` for the unified `StreamPart` format.

```python
# Stream LLM tokens + node state updates
async for part in graph.astream(
    Command(resume=user_message),          # or initial_state on first turn
    config={"configurable": {"thread_id": session_id}},
    stream_mode=["messages", "updates"],   # messages=tokens, updates=node events
    version="v2",
):
    if part["type"] == "messages":
        token, metadata = part["data"]
        yield token.content                # LLM token → SSE / TTS
    elif part["type"] == "updates":
        node_name, state_delta = next(iter(part["data"].items()))
        yield {"node": node_name, "status": "running"}  # live debugger
```

- **Voice:** tokens → Pipecat TTS → audio
- **Chat:** tokens → SSE → browser
- **Live debugger:** `"updates"` stream → SSE → graph UI highlights active node in real time

## Multi-Turn — First Turn vs Resume

```python
from langgraph.types import Command

# First turn — provide full initial state
await graph.ainvoke(initial_state, config={"configurable": {"thread_id": session_id}})

# Every subsequent turn — resume after interrupt()
await graph.ainvoke(
    Command(resume=user_message_text),
    config={"configurable": {"thread_id": session_id}},
)
```

`collect_data` and any other node using `interrupt()` pauses the graph and waits for `Command(resume=...)`. The session handler (voice/chat channel) is responsible for calling resume on each user turn.

---

## Competitive Landscape

| Tool | What it is | Why we don't use it |
|---|---|---|
| **LangGraph Studio** | Desktop debugger for LangGraph code | Debugger only — you still write Python by hand; not a visual builder |
| **LangSmith Fleet** | Enterprise agent management (no-code templates) | Paid/closed, not voice-focused, no BYOK, no multi-tenancy |
| **Flowise** | Visual builder for LangChain text chains | Text-first, not LangGraph-native, no voice/WhatsApp, no BYOK model |
| **Langflow** | Similar to Flowise (Python-based) | Same limitations as Flowise |

**Vaaniq is the first open-source visual LangGraph builder for voice/chat/WhatsApp agents.** All existing tools are either text-only, closed source, or debuggers rather than builders.

---

## What NOT To Do

- **Don't import from `vaaniq-server`** — this package has no server dependency
- **Don't mutate SessionState** — always return `{**state, "field": new_value}`
- **Don't hardcode API keys** — always use `org_keys` passed in from the server
- **Don't build a custom audio pipeline** — voice I/O is Pipecat/LiveKit's job; this package only handles graph logic
- **Don't add node types without registering in NODE_REGISTRY** — the builder will KeyError at runtime
- **Don't put routing logic inside edge definitions** — routing belongs in the condition node; edges just map labels to targets
- **Don't implement the Code node (Tier 3) in v1** — HTTP Request node covers all custom tool use cases for now
- **Don't expose raw LangGraph primitives** (`Send`, `interrupt`) directly as node types — wrap them in user-friendly abstractions (`parallel`, `delay`)
