# vaaniq-voice-server

Standalone voice server for Vaaniq. Handles telephony webhooks (Twilio, Telnyx, Vonage) and runs the LiveKit voice agent worker as a single process.

## What it does

- **Telephony webhooks** — inbound calls, outbound call answers, status callbacks for Twilio, Telnyx, and Vonage
- **LiveKit worker** — connects to LiveKit Cloud and processes voice call jobs (STT → LangGraph → TTS)
- **Room lifecycle** — creates LiveKit rooms, dispatches agents, tears down on call end

## Architecture

```
Inbound call (any provider):
  Twilio/Telnyx/Vonage → POST /webhooks/<provider>/voice/inbound (or GET for Vonage)
                        → creates session + LiveKit room
                        → returns TwiML/TeXML/NCCO dialling into LiveKit SIP room
                        → LiveKit dispatches job to vaaniq-voice worker
                        → worker: STT → LangGraph → TTS

Outbound call (production — LiveKit native):
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
- At least one telephony provider configured (Twilio, Telnyx, or Vonage)
- PostgreSQL running (shared with main API server)

---

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

# Voice server public URL — needed so webhooks can reach your local machine
# Local: use ngrok (see below). Production: your Fly.io / Railway URL.
VOICE_SERVER_URL=https://xxxx.ngrok.io
```

### 2. Expose the voice server (ngrok)

Your telephony provider needs a public URL to hit your local webhooks:

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

Allows your telephony provider to dial into LiveKit rooms via SIP.

1. Go to **Telephony → SIP trunks → Create new trunk**
2. Select **JSON editor → Inbound**
3. Paste:

```json
{
  "name": "vaaniq-inbound",
  "allowedAddresses": ["0.0.0.0/0"]
}
```

> For production, replace `0.0.0.0/0` with your provider's SIP signaling IP ranges.
> Twilio: `54.172.60.0/30`, `54.244.51.0/30`, `54.171.127.192/30`, `35.156.191.128/30`,
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

Enables LiveKit to call users' phones directly without telephony REST API webhooks.

1. Go to **Telephony → SIP trunks → Create new trunk**
2. Select **JSON editor → Outbound**
3. Paste (replace with your provider's SIP domain and credentials):

```json
{
  "name": "vaaniq-outbound",
  "address": "your-account.pstn.twilio.com",
  "numbers": ["+1XXXXXXXXXX"],
  "authUsername": "your-sip-username",
  "authPassword": "your-sip-password"
}
```

4. Click **Create**, copy the trunk ID (e.g. `ST_xxxxxxxxxx`)
5. Set in `.env`:

```env
LIVEKIT_OUTBOUND_SIP_TRUNK_ID=ST_xxxxxxxxxx
```

When this is set, outbound calls use `CreateSIPParticipant` (LiveKit places the call directly — session metadata is preserved correctly). When unset, falls back to the Twilio REST API path.

---

## Telephony Provider Setup

### Twilio

1. Create a Twilio account at [twilio.com](https://twilio.com) and buy a phone number
2. Set these in `.env` (platform-level fallback — orgs can also bring their own via integrations):

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token
```

3. Configure your Twilio phone number:
   - **Voice webhook URL:** `https://your-domain/webhooks/twilio/voice/inbound`
   - **Method:** POST
   - **Status callback URL:** `https://your-domain/webhooks/twilio/voice/status`

Signature verification uses `X-Twilio-Signature` HMAC-SHA1 (automatic via vaaniq-server).

---

### Telnyx

Telnyx offers lower per-minute rates than Twilio and is a drop-in alternative using TeXML (TwiML-compatible XML).

1. Create a Telnyx account at [telnyx.com](https://telnyx.com) and buy a phone number
2. In Telnyx Mission Control Portal → **Messaging → Phone Numbers**, configure:
   - **Connection type:** TeXML Application
   - **Voice webhook URL:** `https://your-domain/webhooks/telnyx/voice/inbound`
   - **Method:** POST
3. (Optional) Enable webhook signature verification:
   - Go to **API Keys & OAuth → Webhook Signing Key**
   - Copy the Ed25519 public key (base64)
   - Set in `.env`:

```env
TELNYX_PUBLIC_KEY=<base64-encoded-ed25519-public-key>
```

When `TELNYX_PUBLIC_KEY` is set, all Telnyx webhooks are verified using Ed25519 signatures. Leave it empty to skip verification (dev mode only).

---

### Vonage (Nexmo)

Vonage uses NCCO (Nexmo Call Control Objects) — JSON arrays instead of XML.

1. Create a Vonage account at [vonage.com](https://vonage.com) and buy a number
2. Create a Vonage Application:
   - Go to **Applications → Create a new application**
   - Enable **Voice** capability
   - **Answer URL:** `https://your-domain/webhooks/vonage/voice/answer` (GET)
   - **Event URL:** `https://your-domain/webhooks/vonage/voice/event` (POST)
3. Link your phone number to the application
4. (Optional) Enable webhook signature verification:
   - In your application → **Voice** → **Signature secret**
   - Set in `.env`:

```env
VONAGE_SIGNATURE_SECRET=your-signature-secret
```

When `VONAGE_SIGNATURE_SECRET` is set, event webhooks are verified using HMAC-SHA256. Answer webhooks are GET requests (no signature on those).

---

## STT / TTS Providers

Configured per phone number in the UI (**Voice Pipelines** page). Falls back to agent defaults, then org defaults.

### STT (Speech-to-Text)

| Provider | Value | Notes |
|---|---|---|
| Deepgram | `deepgram` | Default. Nova 3 for WebRTC, Nova 2 Phone Call for PSTN |
| AssemblyAI | `assemblyai` | Universal-2 model |
| OpenAI Whisper | `openai` | GPT-4o Mini Transcribe (default), Whisper-1 |
| Azure Speech | `azure` | Requires `azure.api_key` + `azure.region` in org keys |
| Sarvam AI | `sarvam` | 11 Indian languages + Hinglish. Auto-detect with `language=unknown` |

### TTS (Text-to-Speech)

| Provider | Value | Notes |
|---|---|---|
| ElevenLabs | `elevenlabs` | Default. Flash v2.5 model (lowest latency) |
| Cartesia | `cartesia` | Sonic 2 (latest). Supports multilingual |
| Deepgram Aura | `deepgram` | Aura-2 voices. Fast, phone-quality |
| Azure TTS | `azure` | Neural voices. Best for Indian regional languages |
| OpenAI TTS | `openai` | TTS-1 / TTS-1 HD / GPT-4o Mini TTS. 12 voices |
| Sarvam AI | `sarvam` | 11 Indian languages. Requires `sarvam` key in org keys |

> **Sarvam AI:** Endpointing delay is automatically set to 70ms instead of the default 300ms.
> Use `language=unknown` to enable automatic Hinglish / code-mixing detection.

Add provider API keys in the **Integrations** page — keys are Fernet-encrypted before storage.

---

## Webhook Endpoints

All webhooks are on `vaaniq-voice-server` (port 8001). No `/v1/` prefix — providers control these URLs.

### Twilio

| Method | Path | Triggered by |
|---|---|---|
| POST | `/webhooks/twilio/voice/inbound` | Call arrives on org's number |
| POST | `/webhooks/twilio/voice/outbound` | Outbound call answered by user |
| POST | `/webhooks/twilio/voice/status` | Call state change (in-progress, completed, failed) |
| POST | `/webhooks/twilio/voice/recording` | Recording ready |

### Telnyx

| Method | Path | Triggered by |
|---|---|---|
| POST | `/webhooks/telnyx/voice/inbound` | Call arrives on org's number |
| POST | `/webhooks/telnyx/voice/status` | Call state change |

### Vonage

| Method | Path | Triggered by |
|---|---|---|
| GET | `/webhooks/vonage/voice/answer` | Call arrives on org's number (returns NCCO) |
| POST | `/webhooks/vonage/voice/event` | Call state change |

### LiveKit

| Method | Path | Triggered by |
|---|---|---|
| POST | `/webhooks/livekit/room` | Room / participant events |

### Health

| Method | Path | |
|---|---|---|
| GET | `/health` | Liveness probe |

---

## Testing Voice Calls

### Preview (browser — no telephony provider needed)

Use the **Voice Preview** panel in the agent builder UI. Opens a browser WebRTC session directly in a LiveKit room — no phone, no SIP trunk needed.

Requirements:
- LiveKit credentials set in `.env`
- Voice server running (port 8001)
- Main API server running (port 8000)

### Inbound call

1. Configure your number's webhook URL (provider-specific, see above)
2. Call the number
3. Watch logs:
   ```
   voice_inbound_routing  session_id=... sip_uri=sip:...@...sip.livekit.cloud
   worker_job_received    session_id=...
   voice_agent_starting   session_id=... stt_provider=... tts_provider=...
   ```

### Outbound call (agent → your phone)

1. Open the agent builder UI
2. Click **Outbound Call**, select your agent and number, enter your phone
3. Your phone rings — answer it
4. Watch logs:
   ```
   livekit_room_created        session_id=...
   voice_agent_starting        session_id=...
   ```

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
  SECRET_KEY=... \
  TWILIO_ACCOUNT_SID=ACxxxx \
  TWILIO_AUTH_TOKEN=xxxx
```

Optional (for Telnyx / Vonage):

```bash
fly secrets set \
  TELNYX_PUBLIC_KEY=<base64-ed25519-public-key> \
  VONAGE_SIGNATURE_SECRET=your-vonage-secret
```
