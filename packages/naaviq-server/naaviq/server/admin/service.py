import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from naaviq.server.admin.constants import PLATFORM_PROVIDER_SCHEMAS
from naaviq.server.admin.exceptions import ProviderNotFound, UnknownProvider
from naaviq.server.admin.repository import PlatformConfigRepository
from naaviq.server.admin.schemas import (
    FieldSchema,
    PlatformConfigResponse,
    ProviderSchema,
    UpsertPlatformConfigRequest,
)
from naaviq.server.core.encryption import encrypt_key
from naaviq.server.models.platform_config import PlatformConfig

log = structlog.get_logger()


def _to_response(pc: PlatformConfig) -> PlatformConfigResponse:
    schema = PLATFORM_PROVIDER_SCHEMAS.get(pc.provider, {})
    return PlatformConfigResponse(
        id=pc.id,
        provider=pc.provider,
        display_name=schema.get("display_name", pc.provider),
        category=schema.get("category", "other"),
        config=pc.config or {},
        enabled=pc.enabled,
        meta=pc.meta or {},
        created_at=pc.created_at,
        updated_at=pc.updated_at,
    )


def get_all_schemas() -> list[ProviderSchema]:
    return [
        ProviderSchema(
            provider=provider,
            display_name=schema["display_name"],
            category=schema["category"],
            description=schema["description"],
            fields=[FieldSchema(**f) for f in schema["fields"]],
        )
        for provider, schema in PLATFORM_PROVIDER_SCHEMAS.items()
    ]


class AdminService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = PlatformConfigRepository(db)

    async def list_configs(self) -> list[PlatformConfigResponse]:
        configs = await self.repo.list_all()
        return [_to_response(c) for c in configs]

    async def upsert(
        self,
        provider: str,
        data: UpsertPlatformConfigRequest,
    ) -> PlatformConfigResponse:
        if provider not in PLATFORM_PROVIDER_SCHEMAS:
            raise UnknownProvider(provider)

        encrypted = encrypt_key(json.dumps(data.credentials)) if data.credentials else encrypt_key("{}")

        pc = await self.repo.upsert(
            provider=provider,
            credentials=encrypted,
            config=data.config,
            enabled=data.enabled,
        )
        await self.db.commit()
        await self.db.refresh(pc)

        from naaviq.server.admin.platform_cache import reload as reload_cache
        await reload_cache(self.db)
        log.info("platform_config_upserted", provider=provider)
        return _to_response(pc)

    async def delete(self, provider: str) -> None:
        deleted = await self.repo.delete(provider)
        if not deleted:
            raise ProviderNotFound()
        await self.db.commit()
        from naaviq.server.admin.platform_cache import reload as reload_cache
        await reload_cache(self.db)
        log.info("platform_config_deleted", provider=provider)
