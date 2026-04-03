"""PROVIDERS registry — canonical metadata for every supported integration.

This lives in vaaniq-tools (not vaaniq-server) so any developer using tools
standalone can know what credential fields each provider needs without
installing the full server stack.

credential_fields: keys stored as secrets (encrypted in server, env vars in standalone use)
config_fields:     keys stored as plain config (non-secret: endpoint, index_name, etc.)
simple_key:        True = org_keys exposes a plain string for this provider
                   False = org_keys exposes a dict with all credential + config fields
                   (simple_key=True keeps backward compat with llm.py / stt / tts nodes)
"""

PROVIDERS: dict[str, dict] = {
    # ── LLM ──────────────────────────────────────────────────────────────────
    "openai": {
        "category": "llm",
        "display_name": "OpenAI",
        "credential_fields": ["api_key"],
        "config_fields": [],
        "simple_key": True,
    },
    "anthropic": {
        "category": "llm",
        "display_name": "Anthropic",
        "credential_fields": ["api_key"],
        "config_fields": [],
        "simple_key": True,
    },
    "gemini": {
        "category": "llm",
        "display_name": "Google Gemini",
        "credential_fields": ["api_key"],
        "config_fields": [],
        "simple_key": True,
    },
    "groq": {
        "category": "llm",
        "display_name": "Groq",
        "credential_fields": ["api_key"],
        "config_fields": [],
        "simple_key": True,
    },
    "azure_openai": {
        "category": "llm",
        "display_name": "Azure OpenAI",
        "credential_fields": ["api_key"],
        "config_fields": ["endpoint", "deployment", "api_version"],
        "simple_key": True,
    },
    "mistral": {
        "category": "llm",
        "display_name": "Mistral",
        "credential_fields": ["api_key"],
        "config_fields": [],
        "simple_key": True,
    },
    # ── STT ──────────────────────────────────────────────────────────────────
    "deepgram": {
        "category": "stt",
        "display_name": "Deepgram",
        "credential_fields": ["api_key"],
        "config_fields": [],
        "simple_key": True,
    },
    "assemblyai": {
        "category": "stt",
        "display_name": "AssemblyAI",
        "credential_fields": ["api_key"],
        "config_fields": [],
        "simple_key": True,
    },
    "sarvam": {
        "category": "stt",
        "display_name": "Sarvam AI",
        "credential_fields": ["api_key"],
        "config_fields": [],
        "simple_key": True,
    },
    # ── TTS ──────────────────────────────────────────────────────────────────
    "elevenlabs": {
        "category": "tts",
        "display_name": "ElevenLabs",
        "credential_fields": ["api_key"],
        "config_fields": [],
        "simple_key": True,
    },
    "cartesia": {
        "category": "tts",
        "display_name": "Cartesia",
        "credential_fields": ["api_key"],
        "config_fields": [],
        "simple_key": True,
    },
    # ── Telephony ─────────────────────────────────────────────────────────────
    "twilio": {
        "category": "telephony",
        "display_name": "Twilio",
        "credential_fields": ["account_sid", "auth_token"],
        "config_fields": [],
        "simple_key": False,
    },
    "vonage": {
        "category": "telephony",
        "display_name": "Vonage",
        "credential_fields": ["api_key", "api_secret"],
        "config_fields": [],
        "simple_key": False,
    },
    "telnyx": {
        "category": "telephony",
        "display_name": "Telnyx",
        "credential_fields": ["api_key"],
        "config_fields": [],
        "simple_key": True,
    },
    # ── Messaging ─────────────────────────────────────────────────────────────
    "gupshup": {
        "category": "messaging",
        "display_name": "Gupshup (WhatsApp)",
        "credential_fields": ["api_key"],
        "config_fields": ["app_name", "source_number"],
        "simple_key": True,
    },
    # ── Apps (OAuth-based tools) ──────────────────────────────────────────────
    "google": {
        "category": "app",
        "display_name": "Google",
        "credential_fields": ["client_id", "client_secret", "refresh_token"],
        "config_fields": [],
        "simple_key": False,
    },
    "hubspot": {
        "category": "app",
        "display_name": "HubSpot",
        "credential_fields": ["access_token"],
        "config_fields": [],
        "simple_key": False,
    },
    "slack": {
        "category": "app",
        "display_name": "Slack",
        "credential_fields": ["bot_token"],
        "config_fields": [],
        "simple_key": False,
    },
    "salesforce": {
        "category": "app",
        "display_name": "Salesforce",
        "credential_fields": ["client_id", "client_secret", "refresh_token"],
        "config_fields": ["instance_url"],
        "simple_key": False,
    },
    "zoho_crm": {
        "category": "app",
        "display_name": "Zoho CRM",
        "credential_fields": ["client_id", "client_secret", "refresh_token"],
        "config_fields": [],
        "simple_key": False,
    },
    "freshdesk": {
        "category": "app",
        "display_name": "Freshdesk",
        "credential_fields": ["api_key"],
        "config_fields": ["subdomain"],
        "simple_key": False,
    },
    "razorpay": {
        "category": "app",
        "display_name": "Razorpay",
        "credential_fields": ["key_id", "key_secret"],
        "config_fields": [],
        "simple_key": False,
    },
    "stripe": {
        "category": "app",
        "display_name": "Stripe",
        "credential_fields": ["secret_key"],
        "config_fields": [],
        "simple_key": False,
    },
    # ── Infrastructure ────────────────────────────────────────────────────────
    "pinecone": {
        "category": "infrastructure",
        "display_name": "Pinecone",
        "credential_fields": ["api_key"],
        "config_fields": ["environment", "index_name"],
        "simple_key": False,
    },
    "qdrant": {
        "category": "infrastructure",
        "display_name": "Qdrant",
        "credential_fields": ["api_key"],
        "config_fields": ["url", "collection_name"],
        "simple_key": False,
    },
    "weaviate": {
        "category": "infrastructure",
        "display_name": "Weaviate",
        "credential_fields": ["api_key"],
        "config_fields": ["url"],
        "simple_key": False,
    },
    "redis": {
        "category": "infrastructure",
        "display_name": "Redis",
        "credential_fields": ["password"],
        "config_fields": ["url"],
        "simple_key": False,
    },
    "postgres": {
        "category": "infrastructure",
        "display_name": "PostgreSQL",
        "credential_fields": ["password"],
        "config_fields": ["host", "port", "database", "user"],
        "simple_key": False,
    },
}

SUPPORTED_PROVIDERS: set[str] = set(PROVIDERS.keys())

# Providers where a live connectivity test is supported
TESTABLE_PROVIDERS: set[str] = {"openai", "anthropic"}


def build_org_keys(provider: str, credentials: dict, config: dict) -> object:
    """Build the value for org_keys[provider] from decrypted credentials + config.

    Returns a plain string for simple_key providers (backward compat with llm.py),
    or a merged dict for complex providers.
    """
    meta = PROVIDERS.get(provider, {})
    if meta.get("simple_key"):
        return credentials.get("api_key", "")
    return {**credentials, **config}
