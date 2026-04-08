from datetime import datetime

from pydantic import field_validator
from vaaniq.server.core.schemas import CustomModel
from vaaniq.server.integrations.constants import PROVIDERS, SUPPORTED_PROVIDERS


class CreateIntegrationRequest(CustomModel):
    provider: str
    display_name: str = ""          # auto-filled from PROVIDERS if empty
    credentials: dict               # plaintext — encrypted before storage, never returned
    config: dict = {}               # non-secret config fields (endpoint, index_name, etc.)

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, v: str) -> str:
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider '{v}'. Supported: {sorted(SUPPORTED_PROVIDERS)}")
        return v

    @field_validator("display_name", mode="before")
    @classmethod
    def default_display_name(cls, v: str, info) -> str:
        if not v:
            provider = info.data.get("provider", "")
            return PROVIDERS.get(provider, {}).get("display_name", provider)
        return v

    @field_validator("credentials")
    @classmethod
    def credentials_not_empty(cls, v: dict) -> dict:
        if not v:
            raise ValueError("credentials cannot be empty")
        return v


class IntegrationResponse(CustomModel):
    id: str
    org_id: str
    provider: str
    category: str
    display_name: str
    config: dict
    status: str
    meta: dict
    created_at: datetime


class TestIntegrationResponse(CustomModel):
    valid: bool
    tested: bool
    error: str | None = None


class OAuthConnectUrlResponse(CustomModel):
    url: str
