from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.database import get_db
from vaaniq.server.agents.models import Agent
from vaaniq.server.auth.dependencies import get_current_user
from vaaniq.server.agents.dependencies import valid_agent_id
from vaaniq.server.agents.service import AgentService
from vaaniq.server.agents.schemas import AgentCreate, AgentResponse, AgentUpdate

router = APIRouter(prefix="/v1/agents", tags=["agents"])


def _to_response(agent: Agent) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        org_id=agent.org_id,
        name=agent.name,
        system_prompt=agent.system_prompt,
        voice_id=agent.voice_id,
        language=agent.language,
        graph_config=agent.graph_config,
        simple_mode=agent.simple_mode,
    )


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    current: tuple = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentResponse]:
    _, org_id = current
    agents = await AgentService(db).list(org_id)
    return [_to_response(a) for a in agents]


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    body: AgentCreate,
    current: tuple = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    _, org_id = current
    agent = await AgentService(db).create(org_id, body)
    return _to_response(agent)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent: Agent = Depends(valid_agent_id)) -> AgentResponse:
    return _to_response(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    body: AgentUpdate,
    agent: Agent = Depends(valid_agent_id),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    updated = await AgentService(db).update(agent.id, agent.org_id, body)
    return _to_response(updated)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent: Agent = Depends(valid_agent_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await AgentService(db).delete(agent.id, agent.org_id)
