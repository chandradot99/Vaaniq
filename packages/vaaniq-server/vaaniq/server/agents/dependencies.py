from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.agents.exceptions import AgentAccessDenied, AgentNotFound
from vaaniq.server.agents.models import Agent
from vaaniq.server.agents.repository import AgentRepository
from vaaniq.server.auth.dependencies import CurrentUser, get_current_user
from vaaniq.server.core.database import get_db


async def valid_agent(
    agent_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """Fetch and validate that agent_id exists and belongs to the current org."""
    agent = await AgentRepository(db).get_by_id(agent_id)
    if not agent:
        raise AgentNotFound()
    if agent.org_id != current.org_id:
        raise AgentAccessDenied()
    return agent
