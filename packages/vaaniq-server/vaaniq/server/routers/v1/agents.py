import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from vaaniq.server.core.database import get_db
from vaaniq.server.models.agent import Agent
from vaaniq.server.models.user import User
from vaaniq.server.routers.v1.auth import get_current_user
from vaaniq.server.schemas.agent import AgentCreate, AgentResponse, AgentUpdate

router = APIRouter(prefix="/v1/agents", tags=["agents"])
log = structlog.get_logger()


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    current: tuple[User, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentResponse]:
    _, org_id = current
    result = await db.execute(
        select(Agent).where(Agent.org_id == org_id, Agent.deleted_at.is_(None))
    )
    agents = result.scalars().all()
    return [AgentResponse(
        id=a.id, org_id=a.org_id, name=a.name, system_prompt=a.system_prompt,
        voice_id=a.voice_id, language=a.language, graph_config=a.graph_config,
        simple_mode=a.simple_mode,
    ) for a in agents]


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentCreate,
    current: tuple[User, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    _, org_id = current
    agent = Agent(id=str(uuid.uuid4()), org_id=org_id, **body.model_dump())
    db.add(agent)
    await db.commit()
    log.info("agent_created", agent_id=agent.id, org_id=org_id)
    return AgentResponse(
        id=agent.id, org_id=agent.org_id, name=agent.name, system_prompt=agent.system_prompt,
        voice_id=agent.voice_id, language=agent.language, graph_config=agent.graph_config,
        simple_mode=agent.simple_mode,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    current: tuple[User, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    _, org_id = current
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id, Agent.deleted_at.is_(None))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentResponse(
        id=agent.id, org_id=agent.org_id, name=agent.name, system_prompt=agent.system_prompt,
        voice_id=agent.voice_id, language=agent.language, graph_config=agent.graph_config,
        simple_mode=agent.simple_mode,
    )


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    current: tuple[User, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    _, org_id = current
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id, Agent.deleted_at.is_(None))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(agent, field, value)
    await db.commit()
    return AgentResponse(
        id=agent.id, org_id=agent.org_id, name=agent.name, system_prompt=agent.system_prompt,
        voice_id=agent.voice_id, language=agent.language, graph_config=agent.graph_config,
        simple_mode=agent.simple_mode,
    )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    current: tuple[User, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    from datetime import datetime, timezone
    _, org_id = current
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id, Agent.deleted_at.is_(None))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    agent.deleted_at = datetime.now(timezone.utc)
    await db.commit()
