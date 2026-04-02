from datetime import datetime
from pydantic import field_validator
from vaaniq.server.core.schemas import CustomModel
from vaaniq.server.api_keys.constants import SUPPORTED_SERVICES


class CreateApiKeyRequest(CustomModel):
    service: str
    key: str  # plaintext — encrypted before storage, never returned

    @field_validator("service")
    @classmethod
    def valid_service(cls, v: str) -> str:
        if v not in SUPPORTED_SERVICES:
            raise ValueError(f"Unsupported service. Supported: {SUPPORTED_SERVICES}")
        return v

    @field_validator("key")
    @classmethod
    def key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("API key cannot be empty")
        return v.strip()


class ApiKeyResponse(CustomModel):
    id: str
    org_id: str
    service: str
    key_hint: str           # e.g. "sk-****...ab" — never the full key
    last_tested_at: datetime | None
    created_at: datetime


class TestApiKeyResponse(CustomModel):
    valid: bool
    tested: bool            # False when live test not supported for this provider
    error: str | None = None
