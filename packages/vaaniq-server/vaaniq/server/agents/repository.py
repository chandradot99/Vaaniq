import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from vaaniq.server.agents.models import Agent


class AgentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, org_id: str, name: str, **kwargs: Any) -> Agent:
        agent = Agent(
            id=str(uuid.uuid4()),
            org_id=org_id,
            name=name,
            **kwargs,
        )
        self.db.add(agent)
        await self.db.flush()
        return agent

    async def get_by_id(self, agent_id: str) -> Agent | None:
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_by_org(self, org_id: str) -> list[Agent]:
        result = await self.db.execute(
            select(Agent)
            .where(Agent.org_id == org_id, Agent.deleted_at.is_(None))
            .order_by(Agent.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, agent_id: str, **fields: Any) -> None:
        await self.db.execute(
            update(Agent)
            .where(Agent.id == agent_id)
            .values(**fields, updated_at=datetime.now(timezone.utc))
        )

    async def soft_delete(self, agent_id: str) -> None:
        await self.db.execute(
            update(Agent)
            .where(Agent.id == agent_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )
