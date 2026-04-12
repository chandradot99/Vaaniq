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
    # Default credentials for this deployment. Each org can connect their own credentials
    # via Integrations; those take priority over these platform-level defaults.
    "twilio": {
        "display_name": "Twilio",
        "category": "voice",
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
    "deepgram": {
        "display_name": "Deepgram",
        "category": "voice",
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
        "category": "voice",
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
        "category": "voice",
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
}

CATEGORIES = ["oauth", "voice", "observability"]
