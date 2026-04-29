from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from naaviq.server.agents.dependencies import valid_agent
from naaviq.server.agents.models import Agent
from naaviq.server.agents.schemas import (
    AgentResponse,
    CreateAgentRequest,
    UpdateAgentRequest,
    UpdateGraphRequest,
    UpdateVoiceConfigRequest,
    VoicePreviewResponse,
)
from naaviq.server.agents.service import AgentService
from naaviq.server.auth.dependencies import CurrentUser, get_current_user
from naaviq.server.core.database import get_db

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
    from naaviq.server.agents.service import _to_response
    return _to_response(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    body: UpdateAgentRequest,
    current: CurrentUser = Depends(get_current_user),
    agent: Agent = Depends(valid_agent),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    return await AgentService(db).update(agent.id, current.org_id, body)


@router.patch("/{agent_id}/voice-config", response_model=AgentResponse)
async def update_agent_voice_config(
    body: UpdateVoiceConfigRequest,
    current: CurrentUser = Depends(get_current_user),
    agent: Agent = Depends(valid_agent),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    return await AgentService(db).update_voice_config(agent.id, current.org_id, body)


@router.put("/{agent_id}/graph", response_model=AgentResponse)
async def update_graph(
    body: UpdateGraphRequest,
    current: CurrentUser = Depends(get_current_user),
    agent: Agent = Depends(valid_agent),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    return await AgentService(db).update_graph(agent.id, current.org_id, body.graph_config)


@router.post("/{agent_id}/voice-preview", response_model=VoicePreviewResponse)
async def start_voice_preview(
    agent: Agent = Depends(valid_agent),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VoicePreviewResponse:
    """
    Start a browser-based voice preview for this agent.

    Creates a LiveKit room, dispatches the voice worker, and returns a
    participant token so the browser can join and talk to the agent.
    No phone or Twilio needed — uses the LiveKit browser SDK.
    """
    return await AgentService(db).start_voice_preview(
        agent=agent,
        user_identity=current.user.id,
    )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    current: CurrentUser = Depends(get_current_user),
    agent: Agent = Depends(valid_agent),
    db: AsyncSession = Depends(get_db),
) -> None:
    await AgentService(db).delete(agent.id, current.org_id)
