# Vaaniq — CLAUDE.md

> Read this file at the start of every session. It has everything needed to understand the project, make good decisions, and write consistent code.

**GitHub:** `github.com/chandradot99/vaaniq`
**Linear:** `linear.app/chandradot99/project/vaaniq-43b1169cf4e7`
**PyPI namespace:** `vaaniq-*`

---

## What We Are Building

**Vaaniq** — an open source AI agent platform. Businesses build and deploy agents that handle phone calls, web chat, and WhatsApp — powered by their own data and API keys. Voice is one channel among many, not the whole product.

**Positioning:** Open source alternative to Vapi / ElevenLabs Agent / Retell AI.

**Key differentiators:**
- Visual LangGraph editor — drag-and-drop agent flow builder (React Flow + LangGraph)
- Multi-channel — voice, web chat, WhatsApp from the same backend
- BYOK/BYOC — clients bring their own keys for every provider
- Indian language support — Hindi, Hinglish, Tamil, Telugu, Marathi + Sarvam AI
- Live session debugger — watch the agent think in real time on the graph
- Composable Python packages — use just what you need
- Self-hostable with Docker Compose

**License:** Apache 2.0 (open source) + paid cloud version

---

## Package Architecture

Vaaniq is built as **multiple composable Python packages** under a shared namespace. This is the most critical architectural decision — it enables independent versioning, isolated testing, and community contributions per package.

```
pip install vaaniq-core      # base classes + SessionState — no external deps
pip install vaaniq-graph     # visual LangGraph execution engine
pip install vaaniq-voice     # voice pipeline (STT → graph → TTS) — Pipecat for PSTN, LiveKit for WebRTC
pip install vaaniq-rag       # RAG pipeline + vector DB connectors
pip install vaaniq-tools     # pre-built tool library (Calendar, CRM, Payments)
pip install vaaniq-channels  # chat (SSE) + WhatsApp channel handlers
pip install vaaniq-server    # FastAPI server — ties all packages together
# Reserved namespace (cloud version only):
pip install vaaniq-billing   # subscription plans, usage metering, Stripe
pip install vaaniq-admin     # admin APIs, org management, impersonation
```

### Package Dependency Tree

```
vaaniq-core                   ← no vaaniq dependencies (foundation)
      ↑
      ├── vaaniq-graph         depends on: core
      ├── vaaniq-rag           depends on: core
      ├── vaaniq-tools         depends on: core
      ├── vaaniq-voice         depends on: core, graph
      └── vaaniq-channels      depends on: core, graph
              ↑
        vaaniq-server          depends on: all packages above
```

### Who Uses What

```
User                    Installs                       Gets
──────────────────────────────────────────────────────────────────
Indie developer         vaaniq-graph                Just the graph engine
                        vaaniq-voice                + voice pipeline
                        (brings their own server)      in their own app

Agency / startup        vaaniq-server               Full self-hosted
                        + docker-compose up             platform + dashboard

End business client     vaaniq.ai (your SaaS)       Hosted cloud version
```

### Why Multiple Packages (Not One Monolith)

1. **Independent versioning** — release `vaaniq-rag` v1.2.0 without touching voice
2. **Isolated testing** — test `vaaniq-graph` with no server, no DB, no voice pipeline
3. **Selective adoption** — developer uses just the graph engine in their own FastAPI app
4. **Community contributions** — add a Qdrant connector to `vaaniq-rag` without touching anything else
5. **Forces good architecture** — `vaaniq-graph` literally cannot import from `vaaniq-server`
6. **Open core business model** — `vaaniq-billing` / `vaaniq-admin` can have stricter licensing later

### vaaniq-tools Optional Dependencies

`vaaniq-tools` covers Calendar, CRM, Payments, Ecommerce, Helpdesk — each group pulls in heavy SDKs. Use optional dependency groups so users only install what they need:

```toml
# packages/vaaniq-tools/pyproject.toml
[project]
name = "vaaniq-tools"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "vaaniq-core>=0.1.0",
    "httpx>=0.27",          # base — used by webhook.py and all tool HTTP calls
]

[project.optional-dependencies]
crm       = ["hubspot-api-client>=9.0", "zoho-crm-sdk>=2.0"]
payments  = ["razorpay>=1.4", "stripe>=7.0"]
calendar  = ["google-api-python-client>=2.0", "caldav>=1.3"]
helpdesk  = ["freshdesk-python>=1.0"]
ecommerce = ["shopifyapi>=12.0", "woocommerce>=3.0"]
messaging = ["twilio>=9.0", "slack-sdk>=3.0"]
dev       = ["pytest>=8.0", "pytest-asyncio>=0.24"]
all       = ["vaaniq-tools[crm,payments,calendar,helpdesk,ecommerce,messaging]"]
```

Install only what you need:
```bash
pip install vaaniq-tools[crm,payments]   # CRM + payments only
pip install vaaniq-tools[all]            # everything
```

---

## Monorepo Structure (`vaaniq` repo — Python only)

```
vaaniq/                              ← GitHub repo root
├── CLAUDE.md                           ← you are here
├── pyproject.toml                      ← uv workspace root
├── docker-compose.yml                  ← full local stack
├── docker-compose.prod.yml             ← production (no bind mounts, resource limits)
├── .env.example
├── README.md
├── LICENSE                             ← Apache 2.0
│
├── .github/
│   └── workflows/
│       ├── ci.yml                  ← lint + test matrix per package on every PR
│       ├── publish.yml             ← PyPI publish on tag (per-package)
│       ├── docker.yml              ← build + push images on main merge
│       └── migrate.yml             ← alembic check + upgrade on deploy
│
├── packages/                           ← Python packages (published to PyPI)
│   │
│   ├── vaaniq-core/
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── vaaniq/core/
│   │       ├── __init__.py
│   │       ├── state.py            ← SessionState TypedDict
│   │       ├── nodes.py            ← BaseNode abstract class
│   │       ├── tools.py            ← BaseTool abstract class
│   │       ├── channels.py         ← BaseChannel abstract class
│   │       ├── vector_db.py        ← BaseVectorDB abstract class
│   │       ├── providers.py        ← BaseLLM, BaseSTT, BaseTTS abstract
│   │       └── config.py           ← AgentConfig schema (Pydantic)
│   │
│   ├── vaaniq-graph/
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── vaaniq/graph/
│   │       ├── __init__.py
│   │       ├── builder.py          ← GraphBuilder: JSON → LangGraph
│   │       ├── runner.py           ← execute graph, emit debug events
│   │       ├── serializer.py       ← graph ↔ JSON serialisation
│   │       └── nodes/              ← built-in node type implementations
│   │           ├── __init__.py     ← NODE_REGISTRY dict
│   │           ├── base.py         ← BaseNode class
│   │           ├── llm_response.py
│   │           ├── condition.py
│   │           ├── collect_data.py
│   │           ├── run_tool.py
│   │           ├── rag_search.py
│   │           ├── transfer_human.py
│   │           ├── end_session.py
│   │           ├── post_session_action.py
│   │           └── guard.py
│   │
│   ├── vaaniq-voice/
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── vaaniq/voice/
│   │       ├── __init__.py
│   │       ├── pipeline.py         ← VoicePipeline abstraction — routes to correct backend
│   │       ├── pipecat.py          ← Pipecat pipeline (PSTN phone calls via Twilio)
│   │       ├── livekit.py          ← LiveKit pipeline (browser WebRTC voice — Sprint 5)
│   │       ├── transport.py        ← Twilio/Vonage/Telnyx transport
│   │       └── providers/
│   │           ├── stt/            ← Deepgram, Whisper, Azure, Sarvam AI
│   │           └── tts/            ← ElevenLabs, Azure, OpenAI TTS, Cartesia
│   │
│   ├── vaaniq-rag/
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── vaaniq/rag/
│   │       ├── __init__.py
│   │       ├── pipeline.py         ← chunk → embed → store / retrieve
│   │       ├── embedder.py         ← text chunking + embedding
│   │       ├── retriever.py        ← similarity search
│   │       ├── sources/            ← data source connectors
│   │       │   ├── base.py
│   │       │   ├── pdf.py          ← pypdf
│   │       │   ├── docx.py         ← python-docx
│   │       │   ├── sheets.py       ← Google Sheets (OAuth)
│   │       │   ├── drive.py        ← Google Drive (OAuth)
│   │       │   ├── notion.py       ← Notion API
│   │       │   ├── airtable.py
│   │       │   └── scraper.py      ← URL / sitemap (BeautifulSoup)
│   │       └── vector_db/          ← vector DB connectors (BYOC)
│   │           ├── base.py         ← VectorDBConnector abstract
│   │           ├── pgvector.py     ← default, no extra service needed
│   │           ├── pinecone.py
│   │           ├── qdrant.py
│   │           ├── weaviate.py
│   │           └── chroma.py
│   │
│   ├── vaaniq-tools/
│   │   ├── pyproject.toml          ← optional dep groups: crm, payments, calendar, helpdesk
│   │   ├── tests/
│   │   └── vaaniq/tools/
│   │       ├── __init__.py
│   │       ├── registry.py         ← TOOL_REGISTRY + dynamic loader
│   │       ├── base.py             ← BaseTool class
│   │       ├── calendar.py         ← Google Calendar, Calendly, Cal.com
│   │       ├── crm.py              ← HubSpot, Zoho, Salesforce, Pipedrive
│   │       ├── payments.py         ← Razorpay (India-first), Stripe
│   │       ├── ecommerce.py        ← Shopify, WooCommerce
│   │       ├── helpdesk.py         ← Freshdesk (India-first), Zendesk
│   │       ├── messaging.py        ← WhatsApp, Slack, SMTP email
│   │       └── webhook.py          ← Generic POST webhook (Zapier/n8n/Make)
│   │
│   ├── vaaniq-channels/
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── vaaniq/channels/
│   │       ├── __init__.py
│   │       ├── base.py             ← BaseChannel abstract
│   │       ├── chat.py             ← SSE streaming chat
│   │       └── whatsapp/
│   │           ├── base.py
│   │           ├── gupshup.py      ← India priority (cheaper)
│   │           └── twilio.py
│   │
│   └── vaaniq-server/
│       ├── pyproject.toml          ← depends on all other packages
│       ├── alembic.ini
│       ├── tests/
│       └── vaaniq/server/
│           ├── __init__.py
│           ├── main.py             ← FastAPI app init + router registration
│           ├── routers/
│           │   └── v1/             ← ALL routes versioned under /v1/
│           │       ├── auth.py         ← /v1/auth/*
│           │       ├── agents.py       ← /v1/agents/*
│           │       ├── graph.py        ← /v1/agents/:id/graph
│           │       ├── sessions.py     ← /v1/sessions/*
│           │       ├── campaigns.py    ← /v1/campaigns/*
│           │       ├── chat.py         ← /v1/chat/* (SSE)
│           │       ├── webhooks.py     ← /webhooks/twilio, /webhooks/whatsapp (no version — Twilio controls this URL)
│           │       ├── knowledge.py    ← /v1/knowledge/*
│           │       ├── tools.py        ← /v1/tools/*
│           │       ├── settings.py     ← /v1/settings/*
│           │       └── debug.py        ← /v1/debug/* (WebSocket live graph)
│           ├── models/             ← SQLAlchemy ORM models
│           │   ├── user.py
│           │   ├── organization.py
│           │   ├── agent.py        ← includes graph_config JSONB field
│           │   ├── session.py      ← unified voice + chat + WhatsApp
│           │   ├── api_key.py      ← encrypted BYOK keys
│           │   ├── phone_number.py
│           │   ├── data_source.py
│           │   ├── tool_config.py
│           │   ├── campaign.py
│           │   ├── audit_log.py    ← who changed what, when
│           │   ├── webhook_delivery.py ← retry tracking
│           │   └── invitation.py   ← org member invites
│           ├── schemas/            ← Pydantic request/response schemas
│           │   ├── auth.py
│           │   ├── agent.py
│           │   ├── session.py
│           │   └── graph.py
│           ├── core/
│           │   ├── config.py       ← pydantic-settings (reads .env)
│           │   ├── database.py     ← SQLAlchemy async engine + session (supports read replica)
│           │   ├── security.py     ← JWT helpers (python-jose)
│           │   ├── encryption.py   ← Fernet BYOK key encrypt/decrypt
│           │   ├── rate_limit.py   ← slowapi rate limiter config
│           │   └── observability.py ← Sentry init, OpenTelemetry setup
│           ├── middleware/
│           │   ├── audit.py        ← log all write operations to audit_logs
│           │   └── cors.py         ← explicit CORS allowlist (never *)
│           ├── workers/            ← Celery background tasks
│           │   ├── celery_app.py
│           │   ├── embedding.py    ← process uploaded docs
│           │   ├── sync.py         ← auto-sync data sources
│           │   ├── campaigns.py    ← outbound calling
│           │   ├── analytics.py    ← aggregate stats hourly
│           │   └── webhooks.py     ← webhook delivery with retry + DLQ
│           └── migrations/         ← Alembic
│               └── versions/
```

---

## Build Tool: `uv` Workspaces

We use **`uv`** (not pip/poetry) for the Python monorepo. It handles workspaces natively and is significantly faster.

```toml
# pyproject.toml (repo root — workspace definition)
[tool.uv.workspace]
members = [
    "packages/vaaniq-core",
    "packages/vaaniq-graph",
    "packages/vaaniq-voice",
    "packages/vaaniq-rag",
    "packages/vaaniq-tools",
    "packages/vaaniq-channels",
    "packages/vaaniq-server",
]
```

Each package has its own `pyproject.toml`:

```toml
# packages/vaaniq-graph/pyproject.toml
[project]
name = "vaaniq-graph"
version = "0.1.0"
description = "Visual LangGraph execution engine for Vaaniq"
requires-python = ">=3.14"
dependencies = [
    "vaaniq-core>=0.1.0",
    "langgraph>=0.2.0",
    "langchain>=0.3.0",
    "langchain-openai>=0.2.0",
    "langchain-anthropic>=0.2.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24"]
```

### Common Commands

```bash
# Install everything (all packages in dev mode)
uv sync

# Run backend server
uv run uvicorn vaaniq.server.main:app --reload

# Run Celery worker
uv run celery -A vaaniq.server.workers.celery_app worker --loglevel=info

# Run all tests
uv run pytest

# Test a single package in isolation (no server, no DB needed)
uv run pytest packages/vaaniq-graph/tests/ -v
uv run pytest packages/vaaniq-rag/tests/ -v

# Test a specific file
uv run pytest packages/vaaniq-graph/tests/nodes/test_condition.py -v

# Check for unapplied migrations (run in CI before deploy)
uv run alembic -c packages/vaaniq-server/alembic.ini check

# Run DB migrations
uv run alembic -c packages/vaaniq-server/alembic.ini upgrade head

# Publish a package to PyPI
uv publish packages/vaaniq-rag/
```

### Package Versioning

```
vaaniq-core      v0.1.0   changes rarely — it's the contract
vaaniq-graph     v0.1.0   new node type = minor bump
vaaniq-rag       v0.1.0   new data source connector = minor bump
vaaniq-tools     v0.1.0   new tool = minor bump
vaaniq-voice     v0.1.0
vaaniq-channels  v0.1.0
vaaniq-server    v0.1.0   ties all packages together
```

Breaking change in `vaaniq-core` → major version bump for all packages.
New Google Sheets connector in `vaaniq-rag` → only `vaaniq-rag` bumps to v0.2.0.

---

## Tech Stack

### Python (per package)
| Package | Key Dependencies |
|---|---|
| vaaniq-core | pydantic only |
| vaaniq-graph | vaaniq-core, langgraph, langchain |
| vaaniq-voice | vaaniq-core, vaaniq-graph, pipecat-ai (PSTN), livekit-agents (WebRTC — Sprint 5) |
| vaaniq-rag | vaaniq-core, langchain, pgvector, pypdf, python-docx, httpx |
| vaaniq-tools | vaaniq-core, httpx (base) + optional groups: crm, payments, calendar, helpdesk, ecommerce, messaging |
| vaaniq-channels | vaaniq-core, vaaniq-graph, httpx |
| vaaniq-server | all packages + fastapi, uvicorn, sqlalchemy, alembic, asyncpg, celery, redis, python-jose, bcrypt, cryptography, pydantic-settings, slowapi, sentry-sdk, opentelemetry-sdk, prometheus-fastapi-instrumentator |

### Infrastructure
| Tool | Purpose |
|---|---|
| PostgreSQL 16 + pgvector | Primary DB + default vector search |
| PgBouncer | Connection pooling (sits in front of Postgres) |
| Redis | Celery broker + session memory + cache |
| MinIO | S3-compatible file storage (self-hosted) / S3 in production |
| Docker Compose | Full stack local + production |
| Railway | Backend + DB hosting (cloud version) |

---

## Core Architecture

### The Central Insight
Every agent's behaviour is a **visual graph** that maps 1:1 to a LangGraph in Python:

```
Visual Graph (React Flow UI)
         ↕  serialise / deserialise
JSON config (stored in PostgreSQL JSONB)
         ↕  GraphBuilder (vaaniq-graph)
LangGraph  (Python, executes at session time)
```

Changing the UI changes the JSON. The JSON becomes the LangGraph. All three are the same thing.

### Channel Architecture
The LangGraph is **channel-agnostic**. Only the I/O layer differs per channel:

```
Voice (PSTN):    Audio → Pipecat STT → text → LangGraph → text → Pipecat TTS → Audio
Voice (WebRTC):  Audio → LiveKit STT → text → LangGraph → text → LiveKit TTS → Audio
Chat:            Text  → LangGraph → text → SSE stream → UI
WhatsApp:  Text  → webhook      → text → LangGraph → text → WhatsApp API → user
```

### SessionState — Shared State (vaaniq-core)

Every node reads from and writes to `SessionState`. **Never mutate — always return a new dict.**

```python
# packages/vaaniq-core/vaaniq/core/state.py
from typing import TypedDict, Optional, List, Any, Literal

class Message(TypedDict):
    role: str           # "agent" or "user"
    content: str
    timestamp: str
    node_id: str

class ToolCall(TypedDict):
    tool_name: str
    input: dict
    output: Any
    called_at: str
    success: bool

class SessionState(TypedDict):
    session_id: str      # call_sid for voice, uuid for chat
    agent_id: str
    org_id: str
    channel: Literal["voice", "chat", "whatsapp", "sms", "telegram"]
    user_id: str         # phone number for voice, user_id for chat
    messages: List[Message]
    current_node: str
    collected: dict      # {"name": "Rahul", "budget": "80L"}
    rag_context: str
    crm_record: Optional[dict]
    tool_calls: List[ToolCall]
    route: Optional[str]
    transfer_to: Optional[str]
    start_time: str
    end_time: Optional[str]
    duration_seconds: Optional[int]
    summary: Optional[str]
    sentiment: Optional[str]       # positive / neutral / negative
    action_items: List[str]
    post_actions_completed: List[str]
    session_ended: bool
    transfer_initiated: bool
    error: Optional[str]
```

### GraphBuilder (vaaniq-graph)

```python
# packages/vaaniq-graph/vaaniq/graph/builder.py
class GraphBuilder:
    def build(self, graph_config: dict, org_keys: dict) -> CompiledGraph:
        workflow = StateGraph(SessionState)
        for node in graph_config["nodes"]:
            handler = NODE_REGISTRY[node["type"]](
                config=node["config"],
                org_keys=org_keys     # BYOK keys injected here
            )
            workflow.add_node(node["id"], handler)
        for edge in graph_config["edges"]:
            if edge.get("condition"):
                workflow.add_conditional_edges(
                    edge["from"],
                    lambda state: state["route"],
                    edge["routes"]
                )
            else:
                workflow.add_edge(edge["from"], edge["to"])
        workflow.set_entry_point("start")
        return workflow.compile()
```

### Node Pattern (vaaniq-graph)

All nodes are **classes** — config and org_keys injected at build time:

```python
# packages/vaaniq-graph/vaaniq/graph/nodes/base.py
class BaseNode:
    def __init__(self, config: dict, org_keys: dict):
        self.config = config
        self.org_keys = org_keys

    async def __call__(self, state: SessionState) -> SessionState:
        raise NotImplementedError
```

---

## Node Types Reference

### Input
- `call_start` — entry point when session begins
- `inbound_message` — triggered on each user turn (chat/WhatsApp)

### Logic
- `llm_response` — agent responds using LLM
  - Config: `instructions`, `rag_enabled`, `tools`, `voice_id`
- `condition` — LLM-based routing
  - Config: `router_prompt`, `routes: [{label, description}]`
  - Writes `state["route"]`; conditional edges read it
- `collect_data` — collect structured fields
  - Config: `fields: [{name, type, prompt, required}]`
  - Writes to `state["collected"]`
- `wait` — pause for user input

### Action
- `run_tool` — call a specific tool immediately (no LLM)
  - Config: `tool`, `input: {field: "{{variable}}"}`
- `transfer_human` — transfer to a real person
  - Config: `transfer_number`, `whisper_template`
- `end_session` — end gracefully
  - Config: `farewell_message`
- `post_session_action` — guaranteed side effects after session ends
  - Config: `actions: ["create_crm_lead", "send_whatsapp_summary"]`

### Special
- `rag_search` — search knowledge base, writes `state["rag_context"]`
- `guard` — global override rule checked every turn

### Template Variable Syntax
Used in `run_tool` input configs:
```
{{user.id}}          → state["user_id"]
{{collected.name}}   → state["collected"]["name"]
{{crm.email}}        → state["crm_record"]["email"]
{{channel}}          → "voice" | "chat" | "whatsapp"
```

---

## BYOK/BYOC

All client API keys encrypted with **Fernet** before storing. Encryption key in server env only, never in DB.

```python
# Store
encrypted = fernet.encrypt(api_key.encode()).decode()

# Load at session start — passed into every node via GraphBuilder
org_keys = {k.service: fernet.decrypt(k.encrypted_key) for k in keys}
graph = GraphBuilder().build(graph_config, org_keys)
```

**Supported providers:**
- **LLM:** OpenAI, Anthropic, Gemini, Groq, Ollama (local), AWS Bedrock, Azure OpenAI, Mistral
- **STT:** Deepgram Nova 2 (default), Whisper, Azure, Google, AssemblyAI, Sarvam AI (Indian languages)
- **TTS:** ElevenLabs (default), Azure, Google, OpenAI TTS, Cartesia
- **Telephony:** Twilio (default), Vonage, Telnyx
- **Vector DB:** pgvector (default), Pinecone, Qdrant, Weaviate, Chroma, Milvus
- **WhatsApp:** Gupshup (India, cheaper), Twilio WhatsApp, Interakt

---

## Database Schema (Key Tables)

All in `vaaniq-server`. Migrations managed by Alembic.

**All mutable tables have `deleted_at TIMESTAMPTZ` for soft deletes. Never hard-delete user data.**

```sql
users           (id, email, name, password_hash, created_at, deleted_at)
organizations   (id, name, owner_id, plan, created_at, deleted_at)
org_members     (org_id, user_id, role)
invitations     (id, org_id, email, role, token, expires_at, accepted_at)

agents          (id, org_id, name, system_prompt, voice_id, language,
                 graph_config JSONB,    ← visual graph stored here
                 simple_mode BOOL, created_at, deleted_at)

api_keys        (id, org_id, service, encrypted_key, last_tested_at)
phone_numbers   (id, org_id, agent_id, number, provider, sid)

sessions        (id, org_id, agent_id, channel, user_id,
                 state_snapshot JSONB,  ← full SessionState at end
                 transcript JSONB,      ← messages array
                 duration_seconds, sentiment, summary,
                 cost_breakdown JSONB, created_at)
-- Indexes: (org_id, created_at DESC), (agent_id, created_at DESC)

data_sources    (id, agent_id, type, source_type, config JSONB,
                 mode,                 ← "rag" or "tool"
                 status, last_synced_at, deleted_at)

tool_configs    (id, agent_id, tool_name, config JSONB, enabled)
campaigns       (id, org_id, agent_id, name, status, schedule JSONB)
campaign_calls  (id, campaign_id, phone_number, status, session_id)

-- Production tables
audit_logs      (id, org_id, user_id, action, resource_type, resource_id,
                 diff JSONB, ip_address, user_agent, created_at)
-- Index: (org_id, created_at DESC), (resource_type, resource_id)

webhook_deliveries (id, org_id, event_type, payload JSONB, attempts INT,
                    last_error TEXT, next_retry_at, delivered_at, created_at)

usage_records   (id, org_id, month DATE, channel, session_count INT,
                 minutes_used INT, tokens_used INT, estimated_cost NUMERIC)
```

---

## API Structure (vaaniq-server)

All routes versioned under `/v1/`. Webhook routes are unversioned — Twilio/WhatsApp control these URLs.

```
POST   /v1/auth/register
POST   /v1/auth/login
POST   /v1/auth/refresh
GET    /v1/auth/me

GET    /v1/agents
POST   /v1/agents
GET    /v1/agents/:id
PUT    /v1/agents/:id
DELETE /v1/agents/:id
GET    /v1/agents/:id/graph          ← load graph JSON
PUT    /v1/agents/:id/graph          ← save graph JSON

GET    /v1/sessions                  ← unified voice + chat log
GET    /v1/sessions/:id

POST   /v1/chat/:agent_id/session
POST   /v1/chat/:agent_id/message    ← SSE streaming response
WS     /v1/chat/:agent_id/ws/:sid

POST   /webhooks/twilio/inbound      ← no version prefix — Twilio-controlled URL
POST   /webhooks/twilio/status
POST   /webhooks/whatsapp

WS     /v1/debug/:session_id         ← live graph state stream

GET    /v1/settings/api-keys
POST   /v1/settings/api-keys
DELETE /v1/settings/api-keys/:id
POST   /v1/settings/api-keys/:id/test

GET    /v1/knowledge/:agent_id
POST   /v1/knowledge/:agent_id/upload
POST   /v1/knowledge/:agent_id/url
POST   /v1/knowledge/:agent_id/sheets
DELETE /v1/knowledge/:agent_id/:id

GET    /v1/campaigns
POST   /v1/campaigns
PUT    /v1/campaigns/:id/start
PUT    /v1/campaigns/:id/pause

GET    /health                       ← liveness probe (always 200 if process is up)
GET    /ready                        ← readiness probe (checks DB + Redis connectivity)
GET    /metrics                      ← Prometheus metrics
```

---

## Security

| Concern | Implementation |
|---|---|
| Rate limiting | `slowapi` — 5 req/s on `/v1/auth/*`, 100 req/s on general API |
| CORS | Explicit allowlist in `middleware/cors.py` — never `*` in production |
| JWT auth | `python-jose` — short-lived access tokens (15 min) + refresh tokens (7 days) |
| API key auth | `X-API-Key` header support alongside JWT — for external integrations |
| BYOK encryption | Fernet — keys never stored or logged in plaintext |
| Audit logging | `middleware/audit.py` — all POST/PUT/DELETE ops logged to `audit_logs` |
| Webhook signatures | Always validate `X-Twilio-Signature` / WhatsApp HMAC before processing |
| Input validation | Pydantic schemas on all endpoints — no raw dict access from request body |

---

## Observability

Wire these up from day one — not as an afterthought.

| Tool | Purpose | Where |
|---|---|---|
| **Sentry** | Error tracking + performance | `core/observability.py` — init on startup |
| **OpenTelemetry** | Distributed tracing | Trace every LangGraph execution, every tool call |
| **Prometheus** | Metrics | `prometheus-fastapi-instrumentator` — exposes `/metrics` |
| **structlog** | Structured logging | Every log line must include `org_id`, `session_id`, `node_id` where relevant |
| `/health` | Liveness probe | Returns 200 if process is running |
| `/ready` | Readiness probe | Returns 200 only when DB + Redis are reachable |

Log schema — every structured log must have:
```python
log.info("node_executed", org_id=..., session_id=..., node_id=..., duration_ms=..., channel=...)
```

---

## Reliability

| Concern | Implementation |
|---|---|
| Webhook deduplication | Store `call_sid` / WhatsApp message ID — ignore duplicates (Twilio delivers twice sometimes) |
| Webhook retry | `webhook_deliveries` table + Celery task with exponential backoff (1s, 5s, 30s, 5min, 30min) |
| Dead letter queue | Failed Celery tasks after max retries go to `celery.dlq` queue — alerting on DLQ size |
| Circuit breaker | LLM/STT/TTS calls wrapped in circuit breaker — fail fast instead of hanging voice pipeline |
| DB connection pool | PgBouncer in transaction mode — max 20 connections per server pod |
| Read replica | `DATABASE_REPLICA_URL` env var — analytics + session read queries go to replica |

---

## CI/CD

Four GitHub Actions workflows in `.github/workflows/`:

**`ci.yml`** — runs on every PR:
- Matrix: test each package in isolation (`vaaniq-core`, `vaaniq-graph`, etc.)
- Lint: `ruff check` + `mypy`
- `alembic check` — fails if unapplied migrations exist

**`publish.yml`** — runs on tag `vaaniq-graph/v*`:
- Build + publish the tagged package to PyPI via `uv publish`
- One workflow, triggered per-package by tag prefix

**`docker.yml`** — runs on merge to `main`:
- Build `vaaniq-server` Docker image
- Push to GitHub Container Registry (ghcr.io)

**`migrate.yml`** — runs on deploy to Railway/production:
- `alembic upgrade head`
- Fails deploy if migration fails

---

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/vaaniq
DATABASE_REPLICA_URL=                        # optional — read replica for analytics

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-jwt-secret-here
FERNET_KEY=your-fernet-key-here
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# CORS — comma-separated list of allowed origins
ALLOWED_ORIGINS=http://localhost:3000,https://app.vaaniq.ai

# File storage
STORAGE_BACKEND=minio                        # minio | s3
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=vaaniq
AWS_S3_BUCKET=                               # used when STORAGE_BACKEND=s3
AWS_REGION=

# Observability
SENTRY_DSN=                                  # set in production
OTEL_EXPORTER_OTLP_ENDPOINT=                 # optional OTLP collector

# App
ENVIRONMENT=development                      # development | production
BACKEND_URL=http://localhost:8000

# Optional: cloud version only — never set for self-hosted
DEFAULT_OPENAI_KEY=
DEFAULT_ELEVENLABS_KEY=
```

---

## Running Locally

```bash
# 1. Clone backend
git clone https://github.com/chandradot99/vaaniq
cd vaaniq

# 2. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install all packages in dev mode (workspace)
uv sync

# 4. Setup env
cp .env.example packages/vaaniq-server/.env
# edit .env

# 5. Run DB migrations
uv run alembic -c packages/vaaniq-server/alembic.ini upgrade head

# 6a. Start backend manually
uv run uvicorn vaaniq.server.main:app --reload        # terminal 1
uv run celery -A vaaniq.server.workers.celery_app worker  # terminal 2

# 6b. OR — full backend stack with Docker
docker-compose up
```

---

## Current Sprint — Sprint 1: Foundation & First Call

**Goal:** One inbound Twilio call → ElevenLabs agent → session logged in DB

| ID | Title | Priority | Order |
|---|---|---|---|
| CHA-5 | Monorepo scaffold — uv workspace + all package skeletons (backend only) | 🔴 Urgent | 1st |
| CHA-6 | PostgreSQL schema + Alembic migrations | 🔴 Urgent | 2nd |
| CHA-7 | Auth system — JWT login, register, protected routes | 🔴 Urgent | 3rd |
| CHA-8 | Twilio inbound → ElevenLabs agent → session logged | 🔴 Urgent | 4th |
| CHA-60 | API versioning + health/ready/metrics endpoints | 🔴 Urgent | 5th |
| CHA-61 | Observability — Sentry, OpenTelemetry, structured logging | 🟠 High | 6th |
| CHA-62 | CI/CD — GitHub Actions workflows | 🟠 High | 7th |
| CHA-10 | Deploy — Railway (backend + DB) | 🟠 High | 8th |

**Note:** Sprint 1 uses ElevenLabs hosted agent for the quickest path to a working call. We replace it with our own Pipecat + LangGraph pipeline in Sprint 4. LiveKit is added in Sprint 5 for browser WebRTC voice. This is intentional — validate first, build the custom pipeline after.

---

## Sprint Roadmap

| Sprint | Focus | Target |
|---|---|---|
| 1 | Foundation + First Call | Apr 2 |
| 2 | Agent Builder Dashboard | Apr 16 |
| 3 | Knowledge Base + RAG (vaaniq-rag) | Apr 30 |
| 4 | Visual LangGraph Editor (vaaniq-graph) | May 14 |
| 4b | Pre-Built Tool Library (vaaniq-tools) | May 21 |
| 5 | Outbound + Chat + WhatsApp + Indian Languages | May 28 |
| 6 | Analytics Dashboard | Jun 11 |
| 7 | Billing + Open Source Release + PyPI publish | Jun 25 |
| 8 | Extended Connectors (vaaniq-rag additions) | Jul 9 |
| 8b | BYOC Infrastructure + Vector DB Alternatives | Jul 16 |
| 9 | Enterprise + White Label + SSO | Jul 23 |
| 10 | Industry Templates + Marketplace | Aug 6 |

Full tickets: https://linear.app/chandradot99/project/vaaniq-43b1169cf4e7

---

## Key Architectural Decisions (Don't Revisit These)

1. **Multiple composable packages** — not one monolith; enables independent versioning, testing, and community adoption
3. **uv workspaces** — modern Python monorepo management; faster than pip/poetry
4. **vaaniq-core has zero vaaniq dependencies** — it's the contract; if it imports from graph or server, you've made a mistake
5. **All API routes under /v1/** — versioned from day one; webhooks (Twilio/WA) are the only exception
6. **FastAPI over Flask/Django** — async is mandatory for concurrent voice + chat sessions
7. **LangGraph over basic LangChain agents** — stateful graph for multi-step flows
8. **Pipecat for PSTN, LiveKit for WebRTC** — Pipecat is simpler for Twilio phone calls (no extra infra); LiveKit handles browser WebRTC voice (Sprint 5); both are open source; never build a custom audio pipeline
9. **Node classes over functions** — config + org_keys injected cleanly at build time
11. **pgvector as default vector DB** — no extra service needed; open source users BYOC others
12. **SessionState not CallState** — unified across voice, chat, WhatsApp, all channels
13. **SSE for chat streaming** — simpler than WebSocket for unidirectional text streaming
14. **Celery for background tasks** — embedding docs, syncing sources, running campaigns
15. **n8n is NOT a dependency** — we POST to webhooks; what runs on the other end is the client's business
16. **Soft deletes everywhere** — `deleted_at` on all mutable tables; never hard-delete user data
17. **Observability from day one** — Sentry + OpenTelemetry + Prometheus wired in Sprint 1, not Sprint 6

---

## India-Specific Priorities

Always keep the Indian market in mind — it's a key differentiator:

- **Indian languages first** — Deepgram + Sarvam AI for STT; ElevenLabs multilingual for TTS
- **Hinglish handling** — Mixed Hindi+English is the norm; STT must handle it gracefully
- **WhatsApp over SMS** — 500M+ Indian users; Gupshup is cheaper than Twilio WhatsApp for India
- **Razorpay over Stripe** — most Indian businesses use Razorpay; add it before Stripe
- **Zoho CRM over Salesforce** — very popular in India, affordable
- **Freshdesk over Zendesk** — Freshworks is Indian; widely used by Indian SMBs
- **Indian phone numbers** — always validate +91XXXXXXXXXX format correctly

---

## What NOT To Do

- **Don't add routes without /v1/ prefix** — exception: `/webhooks/*`, `/health`, `/ready`, `/metrics`
- **Don't put everything in one package** — each package has one clear responsibility
- **Don't let vaaniq-graph import from vaaniq-server** — only upward dependencies allowed
- **Don't use Flask** — FastAPI only; async is required throughout
- **Don't use basic LangChain AgentExecutor** — use LangGraph for all agent logic
- **Don't build custom audio pipeline** — Pipecat handles PSTN, LiveKit handles WebRTC; never roll your own VAD/interruption handling
- **Don't store API keys in plaintext** — always Fernet encrypt before DB
- **Don't mutate SessionState** — always return `{**state, "field": new_value}`
- **Don't block the event loop** — all DB, HTTP, tool calls must be `await`ed
- **Don't hardcode any API keys** — always load from BYOK store at runtime
- **Don't build n8n into the product** — we send webhooks to n8n, we don't embed it
- **Don't hard-delete records** — use `deleted_at` soft delete on all mutable tables
- **Don't use `*` for CORS in production** — explicit allowlist only
- **Don't skip observability** — Sentry DSN and structlog fields are mandatory from Sprint 1
- **Don't trust webhook payloads without signature validation** — always verify Twilio-Signature / WA HMAC

---

## Code Style

- Python: PEP 8, type hints everywhere, async/await throughout
- No `print()` — use `structlog` for structured logging; every log line includes `org_id` and `session_id`
- All FastAPI endpoints return Pydantic schemas, never raw dicts
- All DB queries: `async with get_db() as db`
- Tests in `tests/` inside each package — test in isolation before integration
- Use `pytest-asyncio` for async tests

---

## When Starting a New Feature

**1. Which package does it belong to?**
```
New node type          → packages/vaaniq-graph/vaaniq/graph/nodes/
New RAG data source    → packages/vaaniq-rag/vaaniq/rag/sources/
New vector DB          → packages/vaaniq-rag/vaaniq/rag/vector_db/
New pre-built tool     → packages/vaaniq-tools/vaaniq/tools/
New API endpoint       → packages/vaaniq-server/vaaniq/server/routers/v1/
New channel            → packages/vaaniq-channels/vaaniq/channels/
New STT/TTS provider   → packages/vaaniq-voice/vaaniq/voice/providers/
PSTN voice change      → packages/vaaniq-voice/vaaniq/voice/pipecat.py
WebRTC voice change    → packages/vaaniq-voice/vaaniq/voice/livekit.py
```

**2.** Does `SessionState` need a new field? → edit `vaaniq-core/state.py`

**3.** Write and test the package logic in isolation first

**4.** Wire into `vaaniq-server` last

**5.** DB schema change? → create Alembic migration in `vaaniq-server`; add soft delete + indexes

**6.** New node? → register in `NODE_REGISTRY` in `vaaniq/graph/nodes/__init__.py`

**7.** New tool? → register in `TOOL_REGISTRY` in `vaaniq/tools/registry.py`

**8.** New API endpoint? → place under `routers/v1/`, return Pydantic schema, add rate limit if public-facing

---

*Vaaniq — Last updated: March 31, 2026*
*Update this file whenever major architectural decisions are made.*
