from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from vaaniq.server.agents.models import Agent


class AgentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(self, org_id: str) -> list[Agent]:
        result = await self.db.execute(
            select(Agent).where(Agent.org_id == org_id, Agent.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def get_by_id(self, agent_id: str, org_id: str) -> Agent | None:
        result = await self.db.execute(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.org_id == org_id,
                Agent.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_first_active(self) -> Agent | None:
        result = await self.db.execute(
            select(Agent).where(Agent.deleted_at.is_(None)).limit(1)
        )
        return result.scalar_one_or_none()
