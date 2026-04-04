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
}

CATEGORIES = ["oauth", "observability"]
