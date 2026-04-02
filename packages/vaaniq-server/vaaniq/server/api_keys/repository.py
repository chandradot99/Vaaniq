import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from vaaniq.server.models.api_key import ApiKey


class ApiKeyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, org_id: str, service: str, encrypted_key: str) -> ApiKey:
        key = ApiKey(
            id=str(uuid.uuid4()),
            org_id=org_id,
            service=service,
            encrypted_key=encrypted_key,
        )
        self.db.add(key)
        await self.db.flush()
        return key

    async def get_by_id(self, key_id: str) -> ApiKey | None:
        result = await self.db.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_service(self, org_id: str, service: str) -> ApiKey | None:
        result = await self.db.execute(
            select(ApiKey).where(
                ApiKey.org_id == org_id,
                ApiKey.service == service,
                ApiKey.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_org(self, org_id: str) -> list[ApiKey]:
        result = await self.db.execute(
            select(ApiKey)
            .where(ApiKey.org_id == org_id, ApiKey.deleted_at.is_(None))
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, key_id: str, **fields: Any) -> None:
        await self.db.execute(
            update(ApiKey).where(ApiKey.id == key_id).values(**fields)
        )

    async def soft_delete(self, key_id: str) -> None:
        await self.db.execute(
            update(ApiKey)
            .where(ApiKey.id == key_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )
