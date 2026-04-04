from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolves to packages/vaaniq-server/.env regardless of working directory
_ENV_FILE = Path(__file__).parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    database_url: str = "postgresql+asyncpg://vaaniq:vaaniq@localhost:5432/vaaniq"
    database_replica_url: Optional[str] = None
    redis_url: str = "redis://localhost:6379/0"
    fernet_key: str = ""
    allowed_origins: str = "http://localhost:3000"
    sentry_dsn: Optional[str] = None
    otel_exporter_otlp_endpoint: Optional[str] = None
    environment: str = "development"
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"

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

    # ── LangSmith tracing ─────────────────────────────────────────────────────
    # LangChain reads these from os.environ — setup_observability() pushes them there.
    langsmith_api_key: Optional[str] = None
    langsmith_tracing: str = "false"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "vaaniq"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
