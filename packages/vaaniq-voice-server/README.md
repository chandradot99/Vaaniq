# vaaniq-voice-server

Standalone voice server for Vaaniq. Handles Twilio webhooks and runs the LiveKit voice agent worker as a single process.

## What it does

- **Twilio webhook handlers** — inbound calls, outbound call answers, status callbacks, recordings
- **LiveKit worker** — connects to LiveKit Cloud and processes voice call jobs (STT → LangGraph → TTS)
- **Room lifecycle** — creates LiveKit rooms, dispatches agents, tears down on call end

## Architecture

```
Inbound call:
  Twilio → POST /webhooks/twilio/voice/inbound
         → creates session + LiveKit room
         → returns TwiML: <Dial><Sip>sip:{session_id}@livekit-sip-domain</Sip></Dial>
         → Twilio connects to LiveKit SIP
         → LiveKit dispatches job to vaaniq-voice worker
         → worker: STT → LangGraph → TTS

Outbound call (production):
  POST /v1/voice/calls/outbound (main API server)
         → creates session + LiveKit room
         → dispatches vaaniq-voice agent to room
         → LiveKit CreateSIPParticipant → calls user's phone via outbound SIP trunk
         → user answers → connected to agent in room

Outbound call (Twilio fallback — no outbound SIP trunk):
  POST /v1/voice/calls/outbound
         → creates session + calls Twilio REST API
         → user answers → Twilio hits POST /webhooks/twilio/voice/outbound
         → returns TwiML → Twilio SIP → LiveKit room
         → worker resolves session by phone number lookup
```

## Prerequisites

- LiveKit Cloud account (livekit.io) — free tier works for testing
- Twilio account with at least one phone number
- PostgreSQL running (shared with main API server)

## Local Development

### 1. Environment

Copy from the workspace root:

```bash
cp .env.example packages/vaaniq-server/.env
```

Set these in your `.env`:

```env
# LiveKit Cloud — copy from your project settings at cloud.livekit.io
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxxxxxx
LIVEKIT_API_SECRET=your-secret

# SIP domain — shown on LiveKit Cloud project settings page
LIVEKIT_SIP_DOMAIN=your-project.sip.livekit.cloud

# Voice server public URL — needed so Twilio can hit your webhooks
# Local: use ngrok (see below). Production: your Fly.io / Railway URL.
VOICE_SERVER_URL=https://xxxx.ngrok.io
```

### 2. Expose the voice server (ngrok)

Twilio needs a public URL to hit your webhooks:

```bash
ngrok http 8001
# → copy the https://xxxx.ngrok.io URL into VOICE_SERVER_URL in .env
```

### 3. Start the voice server

```bash
uv run uvicorn vaaniq.voice_server.main:app --port 8001 --reload
```

The voice server starts the LiveKit worker internally — no separate process needed.

On startup you should see:
```
checkpointer_ready
platform_cache_reloaded
graph_cache_prewarm_complete
voice_server_started  voice_server_url=https://xxxx.ngrok.io
```

### 4. Run the main API server (separate terminal)

The main API handles auth, agent config, and the outbound call REST endpoint:

```bash
uv run uvicorn vaaniq.server.main:app --port 8000 --reload
```

---

## LiveKit Cloud Setup

### SIP Inbound Trunk

Allows Twilio to dial into LiveKit rooms via SIP.

1. Go to **Telephony → SIP trunks → Create new trunk**
2. Select **JSON editor → Inbound**
3. Paste:

```json
{
  "name": "vaaniq-inbound",
  "allowedAddresses": ["0.0.0.0/0"]
}
```

> For production, replace `0.0.0.0/0` with Twilio's SIP signaling IP ranges:
> `54.172.60.0/30`, `54.244.51.0/30`, `54.171.127.192/30`, `35.156.191.128/30`,
> `54.65.63.192/30`, `54.169.127.128/30`, `54.252.254.64/30`, `177.71.206.192/30`

4. Click **Create**

### SIP Dispatch Rule

Routes each incoming SIP call to its own LiveKit room and dispatches the voice agent.

1. Go to **Telephony → Dispatch rules → Create new dispatch rule**
2. Select **JSON editor**
3. Paste:

```json
{
  "name": "vaaniq-dispatch",
  "rule": {
    "dispatchRuleIndividual": {
      "roomPrefix": ""
    }
  },
  "roomConfig": {
    "agents": [
      {
        "agentName": "vaaniq-voice"
      }
    ]
  }
}
```

4. Click **Create**

### SIP Outbound Trunk (production outbound calls)

Enables LiveKit to call users' phones directly without Twilio REST API webhooks.

1. Go to **Telephony → SIP trunks → Create new trunk**
2. Select **JSON editor → Outbound**
3. Paste (replace with your Twilio SIP domain and credentials):

```json
{
  "name": "vaaniq-outbound",
  "address": "your-account.pstn.twilio.com",
  "numbers": ["+1XXXXXXXXXX"],
  "authUsername": "your-twilio-sip-username",
  "authPassword": "your-twilio-sip-password"
}
```

4. Click **Create**, copy the trunk ID (e.g. `ST_xxxxxxxxxx`)
5. Set in `.env`:

```env
LIVEKIT_OUTBOUND_SIP_TRUNK_ID=ST_xxxxxxxxxx
```

When this is set, outbound calls use `CreateSIPParticipant` (LiveKit places the call directly into the pre-created room — session metadata is preserved correctly). When unset, falls back to the Twilio REST API path.

---

## Testing Voice Calls

### Preview (browser — no Twilio needed)

Use the **Voice Preview** panel in the agent builder UI. This opens a browser WebRTC session directly in a LiveKit room — no phone, no SIP trunk needed.

Requirements:
- LiveKit credentials set in `.env`
- Voice server running (`port 8001`)
- Main API server running (`port 8000`)

### Inbound call (Twilio phone → agent)

1. Configure your Twilio phone number's Voice webhook:
   - **Webhook URL:** `https://xxxx.ngrok.io/webhooks/twilio/voice/inbound`
   - **Method:** POST
2. Call your Twilio number
3. Watch logs for:
   ```
   voice_inbound_routing  session_id=... sip_uri=sip:...@...sip.livekit.cloud
   worker_job_received    session_id=...
   voice_agent_starting   session_id=...
   ```

### Outbound call (agent → your phone)

1. Open the agent builder UI
2. Click **Outbound Call**, select your agent and Twilio number, enter your phone number
3. Your phone rings — answer it
4. Watch logs for:
   ```
   livekit_room_created       session_id=...
   voice_outbound_answered    session_id=... sip_uri=...
   worker_session_resolved_by_phone  (Twilio fallback path)
   voice_agent_starting       session_id=...
   ```

---

## STT / TTS Providers

Configured per phone number in the UI (Voice Pipelines page). Falls back to agent defaults, then org defaults.

| Provider | STT | TTS |
|---|---|---|
| Deepgram | Nova 2 (default) | Aura |
| ElevenLabs | — | Multilingual v2 (default) |
| Cartesia | — | Sonic |
| Azure | Speech-to-Text | Neural TTS |
| AssemblyAI | Universal | — |
| Sarvam AI | 11 Indian languages | 11 Indian languages |

For Sarvam AI (Indian languages), the endpointing delay is automatically set to 70ms instead of the default 300ms.

---

## Webhook Endpoints

All Twilio webhooks are on `vaaniq-voice-server` (port 8001). No `/v1/` prefix — Twilio controls these URLs.

| Method | Path | Triggered by |
|---|---|---|
| POST | `/webhooks/twilio/voice/inbound` | Twilio — call arrives on org's number |
| POST | `/webhooks/twilio/voice/outbound` | Twilio — outbound call answered by user |
| POST | `/webhooks/twilio/voice/status` | Twilio — call state change (in-progress, completed, failed) |
| POST | `/webhooks/twilio/voice/recording` | Twilio — recording ready |
| POST | `/webhooks/livekit/room` | LiveKit — room/participant events |
| GET  | `/health` | Health check |

---

## Production Deployment (Fly.io)

```bash
fly deploy
```

`fly.toml` points to `packages/vaaniq-voice-server/Dockerfile`. The `CMD` runs uvicorn which starts the LiveKit worker internally via the lifespan hook.

Set secrets on Fly.io:

```bash
fly secrets set \
  LIVEKIT_URL=wss://your-project.livekit.cloud \
  LIVEKIT_API_KEY=APIxxxx \
  LIVEKIT_API_SECRET=your-secret \
  LIVEKIT_SIP_DOMAIN=your-project.sip.livekit.cloud \
  LIVEKIT_OUTBOUND_SIP_TRUNK_ID=ST_xxxx \
  VOICE_SERVER_URL=https://your-app.fly.dev \
  DATABASE_URL=postgresql+asyncpg://... \
  FERNET_KEY=... \
  SECRET_KEY=...
```
