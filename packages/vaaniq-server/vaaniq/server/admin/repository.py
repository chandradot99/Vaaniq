from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaaniq.server.models.platform_config import PlatformConfig


class PlatformConfigRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_provider(self, provider: str) -> PlatformConfig | None:
        result = await self.db.execute(
            select(PlatformConfig).where(PlatformConfig.provider == provider)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[PlatformConfig]:
        result = await self.db.execute(select(PlatformConfig))
        return list(result.scalars().all())

    async def upsert(
        self,
        provider: str,
        credentials: str,
        config: dict,
        enabled: bool,
    ) -> PlatformConfig:
        existing = await self.get_by_provider(provider)
        if existing:
            existing.credentials = credentials
            existing.config = config
            existing.enabled = enabled
            return existing
        new = PlatformConfig(
            provider=provider,
            credentials=credentials,
            config=config,
            enabled=enabled,
        )
        self.db.add(new)
        return new

    async def delete(self, provider: str) -> bool:
        existing = await self.get_by_provider(provider)
        if not existing:
            return False
        await self.db.delete(existing)
        return True
