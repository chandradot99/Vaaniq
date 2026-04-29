# Naaviq — CLAUDE.md

> Read this file at the start of every session. It has everything needed to understand the project, make good decisions, and write consistent code.

**GitHub:** `github.com/chandradot99/naaviq-api`
**Linear:** `linear.app/chandradot99/project/naaviq-43b1169cf4e7`
**PyPI namespace:** `naaviq-*`
**FastAPI best practices:** `github.com/zhanymkanov/fastapi-best-practices`

---

## What We Are Building

**Naaviq** — an open source AI agent platform. Businesses build and deploy agents that handle phone calls, web chat, and WhatsApp — powered by their own data and API keys. Voice is one channel among many, not the whole product.

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

Naaviq is built as **multiple composable Python packages** under a shared namespace. This is the most critical architectural decision — it enables independent versioning, isolated testing, and community contributions per package.

```
pip install naaviq-core      # SessionState + AgentConfig — no external deps
pip install naaviq-graph     # visual LangGraph execution engine
pip install naaviq-voice     # voice pipeline (STT → graph → TTS) — Pipecat for PSTN, LiveKit for WebRTC
pip install naaviq-rag       # RAG pipeline + vector DB connectors
pip install naaviq-tools     # pre-built tool library (Calendar, CRM, Payments)
pip install naaviq-channels  # chat (SSE) + WhatsApp channel handlers
pip install naaviq-server    # FastAPI server — ties all packages together
# Reserved namespace (cloud version only):
pip install naaviq-billing   # subscription plans, usage metering, Stripe
pip install naaviq-admin     # admin APIs, org management, impersonation
```

### Package Dependency Tree

```
naaviq-core                   ← no naaviq dependencies (foundation)
      ↑
      ├── naaviq-graph         depends on: core
      ├── naaviq-rag           depends on: core
      ├── naaviq-tools         depends on: core
      ├── naaviq-voice         depends on: core, graph
      └── naaviq-channels      depends on: core, graph
              ↑
        naaviq-server          depends on: all packages above
```

### Who Uses What

```
User                    Installs                       Gets
──────────────────────────────────────────────────────────────────
Indie developer         naaviq-graph                Just the graph engine
                        naaviq-voice                + voice pipeline
                        (brings their own server)      in their own app

Agency / startup        naaviq-server               Full self-hosted
                        + docker compose up             platform + dashboard

End business client     naaviq.ai (your SaaS)       Hosted cloud version
```

### Why Multiple Packages (Not One Monolith)

1. **Independent versioning** — release `naaviq-rag` v1.2.0 without touching voice
2. **Isolated testing** — test `naaviq-graph` with no server, no DB, no voice pipeline
3. **Selective adoption** — developer uses just the graph engine in their own FastAPI app
4. **Community contributions** — add a Qdrant connector to `naaviq-rag` without touching anything else
5. **Forces good architecture** — `naaviq-graph` literally cannot import from `naaviq-server`
6. **Open core business model** — `naaviq-billing` / `naaviq-admin` can have stricter licensing later

### naaviq-tools Optional Dependencies

`naaviq-tools` covers Calendar, CRM, Payments, Ecommerce, Helpdesk — each group pulls in heavy SDKs. Use optional dependency groups so users only install what they need:

```toml
# packages/naaviq-tools/pyproject.toml
[project]
name = "naaviq-tools"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "naaviq-core>=0.1.0",
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
all       = ["naaviq-tools[crm,payments,calendar,helpdesk,ecommerce,messaging]"]
```

Install only what you need:
```bash
pip install naaviq-tools[crm,payments]   # CRM + payments only
pip install naaviq-tools[all]            # everything
```

---

## Monorepo Structure (`naaviq` repo — Python only)

```
naaviq/                              ← GitHub repo root
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
│   ├── naaviq-core/
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── naaviq/core/
│   │       ├── __init__.py
│   │       ├── state.py            ← SessionState, Message, ToolCall TypedDicts
│   │       └── config.py           ← AgentConfig schema (Pydantic)
│   │
│   ├── naaviq-graph/
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── naaviq/graph/
│   │       ├── __init__.py
│   │       ├── builder.py          ← GraphBuilder: JSON → LangGraph
│   │       ├── state.py            ← GraphSessionState with LangGraph reducers
│   │       ├── resolver.py         ← TemplateResolver: {{variable}} → runtime values
│   │       └── nodes/              ← built-in node type implementations
│   │           ├── __init__.py     ← NODE_REGISTRY dict
│   │           ├── base.py         ← BaseNode abstract class
│   │           ├── llm.py          ← LLM provider factory (OpenAI/Anthropic)
│   │           ├── llm_response.py
│   │           ├── condition.py
│   │           ├── collect_data.py
│   │           ├── run_tool.py     ← stub until naaviq-tools implemented
│   │           ├── rag_search.py   ← stub until naaviq-rag implemented
│   │           ├── http_request.py
│   │           ├── set_variable.py
│   │           ├── transfer_human.py
│   │           ├── end_session.py
│   │           └── post_session_action.py
│   │
│   ├── naaviq-voice/
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── naaviq/voice/
│   │       ├── __init__.py
│   │       ├── pipeline.py         ← VoicePipeline abstraction — routes to correct backend
│   │       ├── pipecat.py          ← Pipecat pipeline (PSTN phone calls via Twilio)
│   │       ├── livekit.py          ← LiveKit pipeline (browser WebRTC voice — Sprint 5)
│   │       ├── transport.py        ← Twilio/Vonage/Telnyx transport
│   │       └── providers/
│   │           ├── stt/            ← Deepgram, Whisper, Azure, Sarvam AI
│   │           └── tts/            ← ElevenLabs, Azure, OpenAI TTS, Cartesia
│   │
│   ├── naaviq-rag/
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── naaviq/rag/
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
│   ├── naaviq-tools/
│   │   ├── pyproject.toml          ← optional dep groups: crm, payments, calendar, helpdesk
│   │   ├── tests/
│   │   └── naaviq/tools/
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
│   ├── naaviq-channels/
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── naaviq/channels/
│   │       ├── __init__.py
│   │       ├── base.py             ← BaseChannel abstract
│   │       ├── chat.py             ← SSE streaming chat
│   │       └── whatsapp/
│   │           ├── base.py
│   │           ├── gupshup.py      ← India priority (cheaper)
│   │           └── twilio.py
│   │
│   └── naaviq-server/
│       ├── pyproject.toml          ← depends on all other packages
│       ├── alembic.ini
│       ├── tests/
│       └── naaviq/server/
│           ├── __init__.py
│           ├── main.py             ← FastAPI app init + router registration
│           ├── exceptions.py       ← global base exceptions (NaaviqException, NotFound, Unauthorized)
│           │
│           ├── auth/               ← auth domain
│           │   ├── config.py       ← AuthConfig — JWT settings decoupled from global settings
│           │   ├── constants.py
│           │   ├── dependencies.py ← get_current_user dependency (reusable across all routes)
│           │   ├── exceptions.py   ← EmailAlreadyExists, InvalidCredentials, InvalidToken
│           │   ├── models.py       ← User, Organization, OrgMember SQLAlchemy models
│           │   ├── repository.py
│           │   ├── router.py       ← /v1/auth/*
│           │   ├── schemas.py      ← RegisterRequest (password validation), LoginRequest, etc.
│           │   └── service.py
│           │
│           ├── agents/             ← agents domain
│           │   ├── constants.py
│           │   ├── dependencies.py ← valid_agent_id dependency (validates + fetches, cached per request)
│           │   ├── exceptions.py   ← AgentNotFound
│           │   ├── models.py       ← Agent SQLAlchemy model (includes graph_config JSONB)
│           │   ├── repository.py
│           │   ├── router.py       ← /v1/agents/*
│           │   ├── schemas.py
│           │   └── service.py
│           │
│           ├── webhooks/           ← webhooks domain (unversioned — Twilio controls these URLs)
│           │   ├── constants.py    ← ELEVENLABS_STREAM_URL
│           │   ├── exceptions.py
│           │   ├── repository.py
│           │   ├── router.py       ← /webhooks/twilio/*
│           │   └── service.py
│           │
│           ├── models/             ← shared models only (cross-domain, not owned by one feature)
│           │   ├── api_key.py      ← encrypted BYOK keys
│           │   └── session.py      ← unified voice + chat + WhatsApp sessions
│           │
│           ├── core/
│           │   ├── config.py       ← global pydantic-settings (reads .env)
│           │   ├── database.py     ← SQLAlchemy async engine + session + naming conventions
│           │   ├── encryption.py   ← Fernet BYOK key encrypt/decrypt
│           │   ├── observability.py← Sentry init, OpenTelemetry setup
│           │   ├── schemas.py      ← CustomModel base (UTC datetime, populate_by_name)
│           │   └── security.py     ← JWT helpers (python-jose)
│           │
│           ├── middleware/
│           │   └── cors.py         ← explicit CORS allowlist (never *)
│           │
│           ├── workers/            ← Celery background tasks (added when needed)
│           │   └── celery_app.py
│           │
│           └── migrations/         ← Alembic
│               └── versions/
│                   └── 20260331_0001_initial_schema.py
```

---

## Build Tool: `uv` Workspaces

We use **`uv`** (not pip/poetry) for the Python monorepo. It handles workspaces natively and is significantly faster.

```toml
# pyproject.toml (repo root — workspace definition)
[tool.uv.workspace]
members = [
    "packages/naaviq-core",
    "packages/naaviq-graph",
    "packages/naaviq-voice",
    "packages/naaviq-rag",
    "packages/naaviq-tools",
    "packages/naaviq-channels",
    "packages/naaviq-server",
]
```

Each package has its own `pyproject.toml`:

```toml
# packages/naaviq-graph/pyproject.toml
[project]
name = "naaviq-graph"
version = "0.1.0"
description = "Visual LangGraph execution engine for Naaviq"
requires-python = ">=3.12"
dependencies = [
    "naaviq-core>=0.1.0",
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
uv run uvicorn naaviq.server.main:app --reload

# Run Celery worker
uv run celery -A naaviq.server.workers.celery_app worker --loglevel=info

# Run all tests
uv run pytest

# Test a single package in isolation (no server, no DB needed)
uv run pytest packages/naaviq-graph/tests/ -v
uv run pytest packages/naaviq-rag/tests/ -v

# Test a specific file
uv run pytest packages/naaviq-graph/tests/nodes/test_condition.py -v

# Check for unapplied migrations (run in CI before deploy)
uv run alembic -c packages/naaviq-server/alembic.ini check

# Run DB migrations
uv run alembic -c packages/naaviq-server/alembic.ini upgrade head

# Publish a package to PyPI
uv publish packages/naaviq-rag/
```

### Package Versioning

```
naaviq-core      v0.1.0   changes rarely — it's the contract
naaviq-graph     v0.1.0   new node type = minor bump
naaviq-rag       v0.1.0   new data source connector = minor bump
naaviq-tools     v0.1.0   new tool = minor bump
naaviq-voice     v0.1.0
naaviq-channels  v0.1.0
naaviq-server    v0.1.0   ties all packages together
```

Breaking change in `naaviq-core` → major version bump for all packages.
New Google Sheets connector in `naaviq-rag` → only `naaviq-rag` bumps to v0.2.0.

---

## Tech Stack

### Python (per package)
| Package | Key Dependencies |
|---|---|
| naaviq-core | pydantic only |
| naaviq-graph | naaviq-core, langgraph, langchain |
| naaviq-voice | naaviq-core, naaviq-graph, pipecat-ai (PSTN), livekit-agents (WebRTC — Sprint 5) |
| naaviq-rag | naaviq-core, langchain, pgvector, pypdf, python-docx, httpx |
| naaviq-tools | naaviq-core, httpx (base) + optional groups: crm, payments, calendar, helpdesk, ecommerce, messaging |
| naaviq-channels | naaviq-core, naaviq-graph, httpx |
| naaviq-server | all packages + fastapi, uvicorn, sqlalchemy, alembic, asyncpg, celery, redis, python-jose, bcrypt, cryptography, pydantic-settings, slowapi, sentry-sdk, opentelemetry-sdk, prometheus-fastapi-instrumentator |

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
         ↕  GraphBuilder (naaviq-graph)
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

### SessionState — Shared State (naaviq-core)

Every node reads from and writes to `SessionState`. **Never mutate — always return a new dict.**

```python
# packages/naaviq-core/naaviq/core/state.py
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

### GraphBuilder (naaviq-graph)

```python
# packages/naaviq-graph/naaviq/graph/builder.py
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

### Node Pattern (naaviq-graph)

All nodes are **classes** — config and org_keys injected at build time:

```python
# packages/naaviq-graph/naaviq/graph/nodes/base.py
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

## Credential Architecture — Platform Settings vs Integrations

There are **two separate credential stores**. Never confuse them.

### 1. Platform Settings (`platform_configs` table) — owner/admin only
- **Scope:** whole deployment (all organisations share these)
- **Who sets it:** owner via `/v1/admin/platform-configs` → "Platform Settings" page in UI
- **What goes here:**
  - OAuth app registrations: Google OAuth client_id/secret, Slack OAuth app
  - Observability: LangSmith tracing key, Sentry DSN
  - Default voice/telephony credentials: Twilio, Deepgram, Cartesia, ElevenLabs
- **Purpose of defaults:** lets orgs use voice without bringing their own keys first

### 2. Integrations (`integrations` table) — per organisation
- **Scope:** per organisation — each org has its own set
- **Who sets it:** org members via `/v1/integrations` → "Integrations" page in UI
- **Categories:** `llm`, `stt`, `tts`, `telephony`, `app`, `infrastructure`, `messaging`
- **What goes here:** org's own OpenAI key, org's Deepgram key, HubSpot token, Google OAuth token, Twilio account, etc.
- **Priority:** org Integration credentials **always take priority** over platform_configs defaults

### Credential loading at session start
```python
# org_keys built from integrations table — passed into every node via GraphBuilder
org_keys = {i.provider: decrypt(i.credentials) for i in org_integrations}
graph = GraphBuilder().build(graph_config, org_keys)
# If org_keys["deepgram"] missing → voice pipeline falls back to platform_configs["deepgram"]
```

All credentials encrypted with **Fernet** before storing. Encryption key in `FERNET_KEY` env var only, never in DB or API responses.

**There is NO table called `api_keys`.** That name is obsolete — it was replaced by the `integrations` table.

### Supported providers (Integrations)
- **LLM:** OpenAI, Anthropic, Gemini, Groq, Mistral, Azure OpenAI
- **STT:** Deepgram (Nova 3), OpenAI Whisper, Sarvam AI (Indian languages)
- **TTS:** Cartesia (Sonic), ElevenLabs, Sarvam AI (Indian languages)
- **Telephony:** Twilio, Telnyx, Vonage
- **Apps:** Google (OAuth — Calendar, Gmail, Drive), Slack, HubSpot, Zoho CRM, Razorpay, Stripe, Freshdesk
- **Infrastructure:** Pinecone, Qdrant, Weaviate
- **Messaging:** Gupshup (WhatsApp, India-first)

---

## Database Schema (Key Tables)

All in `naaviq-server`. Migrations managed by Alembic.

**All mutable tables have `deleted_at TIMESTAMPTZ` for soft deletes. Never hard-delete user data.**

```sql
users           (id, email, name, password_hash, created_at, deleted_at)
organizations   (id, name, owner_id, plan, created_at, deleted_at)
org_members     (org_id, user_id, role)
invitations     (id, org_id, email, role, token, expires_at, accepted_at)

agents          (id, org_id, name, system_prompt, voice_id, language,
                 graph_config JSONB,    ← visual graph stored here
                 simple_mode BOOL, created_at, deleted_at)

-- Per-org credentials (BYOK) — see Credential Architecture section above
integrations    (id, org_id, provider, category, display_name,
                 credentials TEXT,      ← Fernet-encrypted JSON
                 config JSONB,          ← non-secret fields (endpoint, index_name, etc.)
                 status, meta JSONB,    ← key_hint, account_email, last_tested_at
                 created_at, deleted_at)
-- Unique index: (org_id, provider) WHERE deleted_at IS NULL

-- Deployment-wide credentials (admin only) — see Credential Architecture section above
platform_configs (id, provider, credentials TEXT, config JSONB,
                  enabled BOOL, meta JSONB, created_at, updated_at)
-- UNIQUE: provider

phone_numbers   (id, org_id, agent_id, number, provider, sid,
                 voice_config JSONB)   ← per-number STT/TTS/language overrides

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

## API Routing Convention

- All routes versioned under `/v1/` — e.g. `/v1/agents`, `/v1/sessions`
- Webhook routes are unversioned — Twilio/WhatsApp control these URLs (`/webhooks/twilio/*`)
- Probe routes are unversioned — `/health`, `/ready`, `/metrics`
- Actual route definitions live in each domain's `router.py`

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
- Matrix: test each package in isolation (`naaviq-core`, `naaviq-graph`, etc.)
- Lint: `ruff check` + `mypy`
- `alembic check` — fails if unapplied migrations exist

**`publish.yml`** — runs on tag `naaviq-graph/v*`:
- Build + publish the tagged package to PyPI via `uv publish`
- One workflow, triggered per-package by tag prefix

**`docker.yml`** — runs on merge to `main`:
- Build `naaviq-server` Docker image
- Push to GitHub Container Registry (ghcr.io)

**`migrate.yml`** — runs on deploy to Railway/production:
- `alembic upgrade head`
- Fails deploy if migration fails

---

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/naaviq
DATABASE_REPLICA_URL=                        # optional — read replica for analytics

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-jwt-secret-here
FERNET_KEY=your-fernet-key-here
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# CORS — comma-separated list of allowed origins
ALLOWED_ORIGINS=http://localhost:3000,https://app.naaviq.ai

# File storage
STORAGE_BACKEND=minio                        # minio | s3
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=naaviq
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
git clone https://github.com/chandradot99/naaviq
cd naaviq

# 2. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install all packages in dev mode (workspace)
uv sync

# 4. Setup env
cp .env.example packages/naaviq-server/.env
# edit .env

# 5. Run DB migrations
uv run alembic -c packages/naaviq-server/alembic.ini upgrade head

# 6a. Start backend manually
uv run uvicorn naaviq.server.main:app --reload        # terminal 1
uv run celery -A naaviq.server.workers.celery_app worker  # terminal 2

# 6b. OR — full backend stack with Docker
docker compose up
```

---

## Project Tracking

Sprints, tickets, and priorities are managed in Linear — not in this file.

- **Linear:** https://linear.app/chandradot99/project/naaviq-43b1169cf4e7

---

## Key Architectural Decisions (Don't Revisit These)

1. **Multiple composable packages** — not one monolith; enables independent versioning, testing, and community adoption
2. **Domain-based server structure** — each feature area (`auth/`, `agents/`, `webhooks/`) owns its own `router.py`, `service.py`, `repository.py`, `models.py`, `schemas.py`, `dependencies.py`, `exceptions.py`. Only truly shared models go in `models/`. No flat `routers/v1/` folder.
3. **uv workspaces** — modern Python monorepo management; faster than pip/poetry
4. **naaviq-core has zero naaviq dependencies** — it's the contract; if it imports from graph or server, you've made a mistake
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
- **Don't let naaviq-graph import from naaviq-server** — only upward dependencies allowed
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
- **Don't commit or push unless the user explicitly asks** — never auto-commit after finishing a feature

---

## After Every Change

- **Run `uv run pytest packages/naaviq-server/tests/ -v` and fix any failures before considering the task done**
- **Check for Python warnings** — run with `-W error` in CI; deprecation warnings from Pydantic/SQLAlchemy must be fixed, not suppressed

---

## Code Style

- Python: PEP 8, type hints everywhere, async/await throughout
- No `print()` — use `structlog` for structured logging; every log line includes `org_id` and `session_id`
- All FastAPI endpoints return Pydantic schemas, never raw dicts
- All schemas inherit from `CustomModel` (in `core/schemas.py`), not `BaseModel` directly
- Use `@field_validator` for input validation (e.g., password strength) — not ad-hoc checks in service layer
- All DB queries: `async with get_db() as db`
- Tests in `tests/` inside each package — test in isolation before integration
- Use `pytest-asyncio` for async tests

---

## When Starting a New Feature

**1. Which package does it belong to?**
```
New node type          → packages/naaviq-graph/naaviq/graph/nodes/
New RAG data source    → packages/naaviq-rag/naaviq/rag/sources/
New vector DB          → packages/naaviq-rag/naaviq/rag/vector_db/
New pre-built tool     → packages/naaviq-tools/naaviq/tools/
New API endpoint       → packages/naaviq-server/naaviq/server/<domain>/router.py
New channel            → packages/naaviq-channels/naaviq/channels/
New STT/TTS provider   → packages/naaviq-voice/naaviq/voice/providers/
PSTN voice change      → packages/naaviq-voice/naaviq/voice/pipecat.py
WebRTC voice change    → packages/naaviq-voice/naaviq/voice/livekit.py
```

**2.** Does `SessionState` need a new field? → edit `naaviq-core/state.py`

**3.** Write and test the package logic in isolation first

**4.** Wire into `naaviq-server` last

**5.** DB schema change? → create Alembic migration in `naaviq-server`; add soft delete + indexes

**6.** New node? → register in `NODE_REGISTRY` in `naaviq/graph/nodes/__init__.py`

**7.** New tool? → register in `TOOL_REGISTRY` in `naaviq/tools/registry.py`

**8.** New API endpoint? → create a domain folder (`<domain>/router.py`, `service.py`, `repository.py`, `models.py`, `schemas.py`, `dependencies.py`, `exceptions.py`); inherit schemas from `CustomModel`; add rate limit if public-facing

---

*Naaviq — Last updated: April 1, 2026*

## Keeping This File Current

**Claude must update `CLAUDE.md` automatically** (without being asked) whenever:
- A new architectural decision is made or an existing one changes
- The server domain structure gains a new domain folder
- A new package is added or the dependency tree changes
- A pattern is established that future sessions need to follow

Sprints and tickets live in Linear — never add them here.

**Claude must update `README.md` automatically** (without being asked) whenever:
- The quick start steps change
- New providers are supported
- The tech stack changes

Do not update either file for routine code changes (new endpoints within existing domains, bug fixes, new schemas following existing patterns).
