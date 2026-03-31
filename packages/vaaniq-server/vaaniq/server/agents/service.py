import uuid
import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.agents.models import Agent
from vaaniq.server.agents.repository import AgentRepository
from vaaniq.server.agents.schemas import AgentCreate, AgentUpdate

log = structlog.get_logger()


class AgentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AgentRepository(db)

    async def list(self, org_id: str) -> list[Agent]:
        return await self.repo.get_all(org_id)

    async def get(self, agent_id: str, org_id: str) -> Agent:
        agent = await self.repo.get_by_id(agent_id, org_id)
        if not agent:
            raise ValueError("Agent not found")
        return agent

    async def create(self, org_id: str, data: AgentCreate) -> Agent:
        agent = Agent(id=str(uuid.uuid4()), org_id=org_id, **data.model_dump())
        self.db.add(agent)
        await self.db.commit()
        log.info("agent_created", agent_id=agent.id, org_id=org_id)
        return agent

    async def update(self, agent_id: str, org_id: str, data: AgentUpdate) -> Agent:
        agent = await self.repo.get_by_id(agent_id, org_id)
        if not agent:
            raise ValueError("Agent not found")
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(agent, field, value)
        await self.db.commit()
        return agent

    async def delete(self, agent_id: str, org_id: str) -> None:
        agent = await self.repo.get_by_id(agent_id, org_id)
        if not agent:
            raise ValueError("Agent not found")
        agent.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
