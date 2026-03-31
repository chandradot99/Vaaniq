# Vaaniq

Open source AI agent platform. Build and deploy agents that handle phone calls, web chat, and WhatsApp — powered by your own data and API keys.

**Positioning:** Open source alternative to Vapi / ElevenLabs Agent / Retell AI.

---

## Features

- **Visual LangGraph editor** — drag-and-drop agent flow builder (React Flow + LangGraph)
- **Multi-channel** — voice, web chat, WhatsApp from the same backend
- **BYOK/BYOC** — bring your own keys for every provider (LLM, STT, TTS, telephony, vector DB)
- **Indian language support** — Hindi, Hinglish, Tamil, Telugu, Marathi + Sarvam AI
- **Live session debugger** — watch the agent think in real time on the graph
- **Composable Python packages** — use just what you need
- **Self-hostable** — runs fully on Docker Compose

---

## Package Architecture

Vaaniq is built as multiple composable Python packages under a shared `vaaniq` namespace:

| Package | Purpose | PyPI |
|---|---|---|
| `vaaniq-core` | Base classes + `SessionState` — no external deps | `pip install vaaniq-core` |
| `vaaniq-graph` | Visual LangGraph execution engine | `pip install vaaniq-graph` |
| `vaaniq-voice` | Voice pipeline — Pipecat (PSTN) + LiveKit (WebRTC) | `pip install vaaniq-voice` |
| `vaaniq-rag` | RAG pipeline + vector DB connectors | `pip install vaaniq-rag` |
| `vaaniq-tools` | Pre-built tool library (Calendar, CRM, Payments, …) | `pip install vaaniq-tools` |
| `vaaniq-channels` | Chat (SSE) + WhatsApp channel handlers | `pip install vaaniq-channels` |
| `vaaniq-server` | FastAPI server — ties all packages together | self-hosted only |

Install only what you need:

```bash
pip install vaaniq-graph vaaniq-voice          # just the graph + voice pipeline
pip install vaaniq-tools[crm,payments]         # CRM + payments tools only
pip install vaaniq-tools[all]                  # all tools
```

---

## Quick Start (Self-Hosted)

### Prerequisites

- [uv](https://docs.astral.sh/uv/) >= 0.4
- Docker + Docker Compose
- Python 3.14+

### 1. Clone

```bash
git clone https://github.com/chandradot99/vaaniq
cd vaaniq
```

### 2. Install dependencies

```bash
uv python install 3.14
uv sync
```

### 3. Configure environment

```bash
cp .env.example packages/vaaniq-server/.env
```

Edit `packages/vaaniq-server/.env` and set at minimum:

```bash
# Generate a Fernet key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```env
SECRET_KEY=your-jwt-secret
FERNET_KEY=your-fernet-key
```

### 4. Start infrastructure

```bash
docker-compose up postgres redis -d
```

### 5. Run migrations

```bash
uv run alembic -c packages/vaaniq-server/alembic.ini upgrade head
```

### 6. Start the server

```bash
uv run uvicorn vaaniq.server.main:app --reload
```

Server is available at `http://localhost:8000`.  
API docs at `http://localhost:8000/docs` (development only).

### Full stack with Docker

```bash
docker-compose up
```

---

## Development

### Run tests

```bash
# All packages
uv run pytest

# Single package in isolation
uv run pytest packages/vaaniq-core/tests/ -v
uv run pytest packages/vaaniq-graph/tests/ -v

# Server tests
uv run pytest packages/vaaniq-server/tests/ -v
```

### Lint

```bash
uv run ruff check packages/
```

### Add a dependency to a package

```bash
# Edit the relevant packages/<package>/pyproject.toml, then:
uv sync
```

### Create a new migration

```bash
uv run alembic -c packages/vaaniq-server/alembic.ini revision --autogenerate -m "your message"
uv run alembic -c packages/vaaniq-server/alembic.ini upgrade head
```

---

## Supported Providers

| Category | Providers |
|---|---|
| LLM | OpenAI, Anthropic, Gemini, Groq, Ollama, AWS Bedrock, Azure OpenAI, Mistral |
| STT | Deepgram Nova 2, Whisper, Azure, Google, AssemblyAI, Sarvam AI |
| TTS | ElevenLabs, Azure, Google, OpenAI TTS, Cartesia |
| Telephony | Twilio, Vonage, Telnyx |
| Vector DB | pgvector (default), Pinecone, Qdrant, Weaviate, Chroma, Milvus |
| WhatsApp | Gupshup, Twilio WhatsApp, Interakt |
| CRM | HubSpot, Zoho, Salesforce, Pipedrive |
| Payments | Razorpay, Stripe |

---

## Tech Stack

- **Runtime:** Python 3.14, FastAPI, SQLAlchemy (async), Alembic
- **Agent engine:** LangGraph, LangChain
- **Voice:** Pipecat (PSTN), LiveKit (WebRTC)
- **Database:** PostgreSQL 16 + pgvector
- **Queue:** Celery + Redis
- **Observability:** Sentry, OpenTelemetry, Prometheus, structlog

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

## Links

- **GitHub:** [github.com/chandradot99/vaaniq](https://github.com/chandradot99/vaaniq)
- **Issues:** [github.com/chandradot99/vaaniq/issues](https://github.com/chandradot99/vaaniq/issues)
- **Linear:** [linear.app/chandradot99/project/vaaniq](https://linear.app/chandradot99/project/vaaniq-43b1169cf4e7)
