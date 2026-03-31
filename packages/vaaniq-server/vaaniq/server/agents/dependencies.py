from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.database import get_db
from vaaniq.server.auth.dependencies import get_current_user
from vaaniq.server.agents.repository import AgentRepository
from vaaniq.server.agents.exceptions import AgentNotFound
from vaaniq.server.agents.models import Agent
from vaaniq.server.auth.models import User


async def valid_agent_id(
    agent_id: str,
    current: tuple[User, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """
    Validates that the agent exists and belongs to the current user's org.
    Reusable across any route that takes :agent_id in the path.
    FastAPI caches this dependency per request — called only once even if used multiple times.
    """
    _, org_id = current
    agent = await AgentRepository(db).get_by_id(agent_id, org_id)
    if not agent:
        raise AgentNotFound()
    return agent
