from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.database import get_db
from vaaniq.server.auth.dependencies import get_current_user, CurrentUser
from vaaniq.server.agents.dependencies import valid_agent
from vaaniq.server.agents.models import Agent
from vaaniq.server.agents.service import AgentService
from vaaniq.server.agents.schemas import (
    AgentResponse,
    CreateAgentRequest,
    UpdateAgentRequest,
    UpdateGraphRequest,
)

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: CreateAgentRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    return await AgentService(db).create(current.org_id, body)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentResponse]:
    return await AgentService(db).list(current.org_id)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent: Agent = Depends(valid_agent),
) -> AgentResponse:
    from vaaniq.server.agents.service import _to_response
    return _to_response(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    body: UpdateAgentRequest,
    current: CurrentUser = Depends(get_current_user),
    agent: Agent = Depends(valid_agent),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    return await AgentService(db).update(agent.id, current.org_id, body)


@router.put("/{agent_id}/graph", response_model=AgentResponse)
async def update_graph(
    body: UpdateGraphRequest,
    current: CurrentUser = Depends(get_current_user),
    agent: Agent = Depends(valid_agent),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    return await AgentService(db).update_graph(agent.id, current.org_id, body.graph_config)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    current: CurrentUser = Depends(get_current_user),
    agent: Agent = Depends(valid_agent),
    db: AsyncSession = Depends(get_db),
) -> None:
    await AgentService(db).delete(agent.id, current.org_id)
