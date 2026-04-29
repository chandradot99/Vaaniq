from datetime import datetime
from typing import Any

from pydantic import BaseModel

from naaviq.server.core.schemas import CustomModel


class FieldSchema(CustomModel):
    key: str
    label: str
    secret: bool
    required: bool
    placeholder: str = ""
    default: str = ""


class ProviderSchema(CustomModel):
    provider: str
    display_name: str
    category: str
    description: str
    fields: list[FieldSchema]


class PlatformConfigResponse(CustomModel):
    id: str
    provider: str
    display_name: str
    category: str
    config: dict[str, Any]       # non-secret fields only — never returns credentials
    enabled: bool
    meta: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class UpsertPlatformConfigRequest(BaseModel):
    """
    credentials: dict of secret field values (client_secret, api_key, dsn …)
    config:      dict of non-secret field values (client_id, redirect_uri …)
    enabled:     whether this provider is active
    """
    credentials: dict[str, str] = {}
    config: dict[str, str] = {}
    enabled: bool = True
