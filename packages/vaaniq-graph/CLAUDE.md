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
          { "name": "name", "type": "string", "prompt": "May I have your name?",         "required": true },
          { "name": "date", "type": "date",   "prompt": "What date works for you?",      "required": true }
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
- All conditional edges from the same source node must share a matching condition node as source
- `entry_point` must match the `id` of a node in `nodes`

---

## Node Types

These are the building blocks exposed in the visual UI. Every `type` string maps to a class in `NODE_REGISTRY`.

| Type | What it does | Key config fields |
|---|---|---|
| `llm_response` | Agent speaks using an LLM; optionally calls tools | `instructions`, `tools[]`, `rag_enabled`, `voice_id` |
| `condition` | LLM-based routing — sets `state["route"]` | `router_prompt`, `routes[{label, description}]` |
| `collect_data` | Gather structured fields from user | `fields[{name, type, prompt, required}]` |
| `run_tool` | Call a specific tool directly (no LLM decision) | `tool`, `input{field: "{{var}}"}` |
| `rag_search` | Search knowledge base, write to `state["rag_context"]` | `top_k`, `min_score` |
| `transfer_human` | Hand off to a real agent | `transfer_number`, `whisper_template` |
| `end_session` | End gracefully | `farewell_message` |
| `post_session_action` | Side effects after session ends (Celery task) | `actions[]` |
| `guard` | Global override checked every turn | `condition_prompt`, `action`, `target_node` |

**Adding a new node type:**
1. Create `vaaniq/graph/nodes/<type>.py` with a class extending `BaseNode`
2. Register it in `NODE_REGISTRY` in `vaaniq/graph/nodes/__init__.py`
3. Add the React Flow node component in the frontend

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

**Never mutate state — always return `{**state, "field": new_value}`.**

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

        workflow.set_entry_point(graph_config["entry_point"])

        checkpointer = PostgresSaver.from_conn_string(settings.database_url)
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

Used in `run_tool` input configs to inject runtime state values:

```
{{collected.name}}    →  state["collected"]["name"]
{{collected.date}}    →  state["collected"]["date"]
{{user.id}}           →  state["user_id"]
{{crm.email}}         →  state["crm_record"]["email"]
{{channel}}           →  "voice" | "chat" | "whatsapp"
```

Resolved by `TemplateResolver` at node call time, before the tool is invoked.

---

## Guard Nodes — Global Overrides

Guards are checked on every turn before the main graph executes. They form a preamble subgraph compiled ahead of the main graph.

```
Every turn:
  → run guards (anger detection, profanity, off-topic, etc.)
  → if triggered: jump to configured target node (e.g. transfer_human)
  → if all clean: enter main graph at current node
```

A guard config:
```json
{
  "type": "guard",
  "config": {
    "condition_prompt": "Is the user expressing anger or frustration?",
    "action": "transfer",
    "target_node": "transfer_human"
  }
}
```

Multiple guards run in order — first match wins.

---

## Simple Mode

`simple_mode: true` on the agent means the user only fills in a system prompt + selects tools. The backend auto-generates a minimal `graph_config`:

```
Start → LLM Response (with user's system prompt + tools) → End
```

Same `GraphBuilder`, same runtime. Simple mode is just a convenience shorthand that skips the visual canvas.

---

## Streaming

```python
# Stream both tokens and node execution events
async for event in graph.astream_events(initial_state, config={"configurable": {"thread_id": session_id}}):
    if event["event"] == "on_chat_model_stream":
        yield event["data"]["chunk"].content   # token for SSE/TTS
    if event["event"] == "on_chain_start":
        yield {"node": event["name"], "status": "running"}  # live debugger
```

- **Voice:** tokens → Pipecat TTS → audio
- **Chat:** tokens → SSE → browser
- **Live debugger:** node execution events → SSE → graph UI highlights active node

---

## What NOT To Do

- **Don't import from `vaaniq-server`** — this package has no server dependency
- **Don't mutate SessionState** — always return `{**state, "field": new_value}`
- **Don't hardcode API keys** — always use `org_keys` passed in from the server
- **Don't build a custom audio pipeline** — voice I/O is Pipecat/LiveKit's job; this package only handles graph logic
- **Don't add node types without registering in NODE_REGISTRY** — the builder will KeyError at runtime
- **Don't put routing logic inside edge definitions** — routing belongs in the condition node; edges just map labels to targets
