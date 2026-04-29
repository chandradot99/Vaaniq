from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from naaviq.server.core.env import ENV_FILE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str = "postgresql+asyncpg://naaviq:naaviq@localhost:5432/naaviq"
    database_replica_url: Optional[str] = None
    redis_url: str = "redis://localhost:6379/0"
    fernet_key: str = ""
    allowed_origins: str = "http://localhost:3000"
    sentry_dsn: Optional[str] = None
    otel_exporter_otlp_endpoint: Optional[str] = None
    environment: str = "development"
    backend_url: str = "http://localhost:8000"
    voice_server_url: str = "http://localhost:8001"  # VOICE_SERVER_URL — Fly.io URL in production
    frontend_url: str = "http://localhost:3000"

    # ── LiveKit (voice pipeline) ──────────────────────────────────────────────
    # Cloud: wss://<project>.livekit.cloud  |  Self-hosted: wss://your-livekit:7880
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    # SIP domain: <project>.sip.livekit.cloud (derived automatically if not set)
    livekit_sip_domain: str = ""
    # Outbound SIP trunk ID — created in LiveKit Cloud dashboard (Telephony → SIP trunks → Outbound)
    # Used by CreateSIPParticipant to place outbound calls via Twilio SIP
    livekit_outbound_sip_trunk_id: str = ""

    # ── OAuth provider credentials ────────────────────────────────────────────
    # Self-hosted deployments must register their own OAuth apps with each provider
    # because OAuth requires pre-registered redirect URIs per deployment domain.
    # See the setup instructions in each provider file under integrations/oauth/providers/.

    # Google — register at https://console.cloud.google.com → APIs & Services → Credentials
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/v1/integrations/oauth/google/callback"

    # Slack — register at https://api.slack.com/apps (future)
    # slack_oauth_client_id: str = ""
    # slack_oauth_client_secret: str = ""

    # ── Twilio (platform-level fallback — orgs bring their own via integrations) ─
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    # ── Telnyx webhook signature verification ────────────────────────────────
    # Ed25519 public key from Telnyx Mission Control Portal → API Keys → Webhook Signing Key
    # Base64-encoded. Leave empty to disable signature verification (dev only).
    telnyx_public_key: str = ""

    # ── Vonage webhook signature verification ────────────────────────────────
    # Signature secret from Vonage Dashboard → Your Applications → Edit → Capabilities → Voice
    # Leave empty to disable signature verification (dev only).
    vonage_signature_secret: str = ""

    # ── LangSmith tracing ─────────────────────────────────────────────────────
    # LangChain reads these from os.environ — setup_observability() pushes them there.
    langsmith_api_key: Optional[str] = None
    langsmith_tracing: str = "false"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "naaviq"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
