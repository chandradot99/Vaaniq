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
    # ── OAuth providers ────────────────────────────────────────────────────────
    "google": {
        "display_name": "Google",
        "category": "oauth",
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
        "category": "oauth",
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
        "category": "observability",
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
                "default": "vaaniq",
                "placeholder": "vaaniq",
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
        "category": "observability",
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
    # Platform-level defaults — orgs can override by adding their own keys in Integrations.
    "twilio": {
        "display_name": "Twilio",
        "category": "voice",
        "description": "Platform-level Twilio account for inbound/outbound calls. Orgs can bring their own Twilio credentials via Integrations.",
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
    "deepgram": {
        "display_name": "Deepgram",
        "category": "voice",
        "description": "STT (Nova-2) and TTS (Aura) for voice calls. One API key covers both. Used as default STT and TTS fallback when Cartesia is not configured.",
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
        "category": "voice",
        "description": "Low-latency text-to-speech. First-choice TTS provider — used when an org has not connected their own key.",
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
        "category": "voice",
        "description": "Realistic TTS with voice cloning support. Used as fallback when Cartesia is not configured.",
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
}

CATEGORIES = ["oauth", "voice", "observability"]
