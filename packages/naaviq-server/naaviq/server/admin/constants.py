"""Platform provider schema registry.

Each entry defines:
  display_name  — shown in admin UI
  category      — groups providers in the UI
  description   — short explanation shown below the provider name
  fields        — list of config fields the admin must fill in
    key         — field key stored in config (non-secret) or credentials (secret)
    label       — shown as form label
    secret      — True = stored encrypted in credentials, False = stored in config JSONB
    required    — whether the field must be non-empty to save
    placeholder — optional hint shown in the input
    default     — optional default value pre-filled in the form
"""

PLATFORM_PROVIDER_SCHEMAS: dict[str, dict] = {
    # ── App setup ─────────────────────────────────────────────────────────────
    # Full app registrations that require multiple credentials (Client ID,
    # Account SID, etc.) — not just a single API key.
    "google": {
        "display_name": "Google",
        "category": "app",
        "description": "Required for Google Calendar, Gmail, and Drive integrations via OAuth.",
        "fields": [
            {
                "key": "client_id",
                "label": "Client ID",
                "secret": False,
                "required": True,
                "placeholder": "123456789.apps.googleusercontent.com",
            },
            {
                "key": "client_secret",
                "label": "Client Secret",
                "secret": True,
                "required": True,
                "placeholder": "GOCSPX-...",
            },
            {
                "key": "redirect_uri",
                "label": "Redirect URI",
                "secret": False,
                "required": True,
                "default": "http://localhost:8000/v1/integrations/oauth/google/callback",
                "placeholder": "https://your-domain.com/v1/integrations/oauth/google/callback",
            },
        ],
    },
    "slack": {
        "display_name": "Slack",
        "category": "app",
        "description": "Required for Slack bot and messaging integrations.",
        "fields": [
            {
                "key": "client_id",
                "label": "Client ID",
                "secret": False,
                "required": True,
                "placeholder": "1234567890.1234567890",
            },
            {
                "key": "client_secret",
                "label": "Client Secret",
                "secret": True,
                "required": True,
                "placeholder": "abcdef1234567890",
            },
            {
                "key": "redirect_uri",
                "label": "Redirect URI",
                "secret": False,
                "required": True,
                "default": "http://localhost:8000/v1/integrations/oauth/slack/callback",
                "placeholder": "https://your-domain.com/v1/integrations/oauth/slack/callback",
            },
        ],
    },
    # ── Observability ──────────────────────────────────────────────────────────
    "langsmith": {
        "display_name": "LangSmith",
        "category": "app",
        "description": "LangSmith tracing for debugging agent runs.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "lsv2_pt_...",
            },
            {
                "key": "project",
                "label": "Project Name",
                "secret": False,
                "required": False,
                "default": "naaviq",
                "placeholder": "naaviq",
            },
            {
                "key": "endpoint",
                "label": "Endpoint",
                "secret": False,
                "required": False,
                "default": "https://api.smith.langchain.com",
                "placeholder": "https://api.smith.langchain.com",
            },
        ],
    },
    "sentry": {
        "display_name": "Sentry",
        "category": "app",
        "description": "Error tracking and performance monitoring.",
        "fields": [
            {
                "key": "dsn",
                "label": "DSN",
                "secret": True,
                "required": True,
                "placeholder": "https://...@sentry.io/...",
            },
        ],
    },
    # ── Voice providers ────────────────────────────────────────────────────────
    # Default credentials for this deployment. Each org can connect their own credentials
    # via Integrations; those take priority over these platform-level defaults.
    "twilio": {
        "display_name": "Twilio",
        "category": "app",
        "description": "Default Twilio account for this deployment. Used for inbound/outbound calls unless an organisation has connected their own Twilio credentials.",
        "fields": [
            {
                "key": "account_sid",
                "label": "Account SID",
                "secret": False,
                "required": True,
                "placeholder": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            },
            {
                "key": "auth_token",
                "label": "Auth Token",
                "secret": True,
                "required": True,
                "placeholder": "your_auth_token",
            },
            {
                "key": "webhook_url",
                "label": "Public Webhook URL",
                "secret": False,
                "required": True,
                "placeholder": "https://your-domain.com",
                "default": "http://localhost:8000",
            },
        ],
    },
    # ── LLM providers ─────────────────────────────────────────────────────────
    "openai": {
        "display_name": "OpenAI",
        "category": "provider",
        "description": "Default OpenAI credentials for this deployment. Used for LLM nodes unless an organisation has connected their own OpenAI key.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "sk-proj-...",
            },
        ],
    },
    "anthropic": {
        "display_name": "Anthropic",
        "category": "provider",
        "description": "Default Anthropic credentials for this deployment. Used for LLM nodes unless an organisation has connected their own Anthropic key.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "sk-ant-...",
            },
        ],
    },
    "groq": {
        "display_name": "Groq",
        "category": "provider",
        "description": "Default Groq credentials for this deployment. Used for LLM nodes unless an organisation has connected their own Groq key.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "gsk_...",
            },
        ],
    },
    "gemini": {
        "display_name": "Google Gemini",
        "category": "provider",
        "description": "Default Gemini credentials for this deployment. Used for LLM nodes unless an organisation has connected their own Gemini key.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "AIza...",
            },
        ],
    },
    "mistral": {
        "display_name": "Mistral",
        "category": "provider",
        "description": "Default Mistral credentials for this deployment. Used for LLM nodes unless an organisation has connected their own Mistral key.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "...",
            },
        ],
    },
    # ── Voice providers ────────────────────────────────────────────────────────
    "deepgram": {
        "display_name": "Deepgram",
        "category": "provider",
        "description": "Default STT provider for this deployment. Used for voice calls where an organisation has not connected their own Deepgram credentials.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "your_deepgram_api_key",
            },
        ],
    },
    "cartesia": {
        "display_name": "Cartesia",
        "category": "provider",
        "description": "Default TTS provider for this deployment. Used for voice calls where an organisation has not connected their own Cartesia credentials.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "your_cartesia_api_key",
            },
        ],
    },
    "elevenlabs": {
        "display_name": "ElevenLabs",
        "category": "provider",
        "description": "Default ElevenLabs TTS for this deployment. Used for voice calls where an organisation has not connected their own ElevenLabs credentials.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "your_elevenlabs_api_key",
            },
        ],
    },
    "sarvam": {
        "display_name": "Sarvam AI",
        "category": "provider",
        "description": "Default STT and TTS for Indian languages (Hindi, Tamil, Telugu, Marathi, Bengali, Gujarati, Kannada, Malayalam). Used for voice calls where an organisation has not connected their own Sarvam credentials.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "your_sarvam_api_key",
            },
        ],
    },
    "telnyx": {
        "display_name": "Telnyx",
        "category": "app",
        "description": "Default Telnyx account for this deployment. Used for inbound/outbound calls unless an organisation has connected their own Telnyx credentials.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "KEY...",
            },
        ],
    },
    "gupshup": {
        "display_name": "Gupshup",
        "category": "app",
        "description": "Default Gupshup account for this deployment. Used for WhatsApp messaging unless an organisation has connected their own Gupshup credentials.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": True,
                "required": True,
                "placeholder": "your_gupshup_api_key",
            },
        ],
    },
    "vonage": {
        "display_name": "Vonage",
        "category": "app",
        "description": "Default Vonage account for this deployment. Used for inbound/outbound calls unless an organisation has connected their own Vonage credentials.",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "secret": False,
                "required": True,
                "placeholder": "your_vonage_api_key",
            },
            {
                "key": "api_secret",
                "label": "API Secret",
                "secret": True,
                "required": True,
                "placeholder": "your_vonage_api_secret",
            },
        ],
    },
}

CATEGORIES = ["provider", "app"]
