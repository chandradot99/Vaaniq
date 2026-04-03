import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from vaaniq.server.models.integration import Integration


class IntegrationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        org_id: str,
        provider: str,
        category: str,
        display_name: str,
        credentials: str,
        config: dict,
    ) -> Integration:
        integration = Integration(
            id=str(uuid.uuid4()),
            org_id=org_id,
            provider=provider,
            category=category,
            display_name=display_name,
            credentials=credentials,
            config=config,
        )
        self.db.add(integration)
        await self.db.flush()
        return integration

    async def get_by_id(self, integration_id: str) -> Integration | None:
        result = await self.db.execute(
            select(Integration).where(
                Integration.id == integration_id,
                Integration.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_provider(self, org_id: str, provider: str) -> Integration | None:
        result = await self.db.execute(
            select(Integration).where(
                Integration.org_id == org_id,
                Integration.provider == provider,
                Integration.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_org(self, org_id: str) -> list[Integration]:
        result = await self.db.execute(
            select(Integration)
            .where(Integration.org_id == org_id, Integration.deleted_at.is_(None))
            .order_by(Integration.category, Integration.created_at)
        )
        return list(result.scalars().all())

    async def update(self, integration_id: str, **fields: Any) -> None:
        await self.db.execute(
            update(Integration).where(Integration.id == integration_id).values(**fields)
        )

    async def soft_delete(self, integration_id: str) -> None:
        await self.db.execute(
            update(Integration)
            .where(Integration.id == integration_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )
