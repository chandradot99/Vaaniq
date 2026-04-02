from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from vaaniq.server.core.database import get_db
from vaaniq.server.auth.dependencies import get_current_user, CurrentUser
from vaaniq.server.agents.dependencies import valid_agent
from vaaniq.server.agents.models import Agent
from vaaniq.server.chat import service
from vaaniq.server.chat.schemas import StartChatResponse, SendMessageRequest, SendMessageResponse

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.post("/{agent_id}/start", response_model=StartChatResponse)
async def start_chat(
    agent: Agent = Depends(valid_agent),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StartChatResponse:
    return await service.start_session(agent.id, current.org_id, db)


@router.post("/message", response_model=SendMessageResponse)
async def send_message(
    body: SendMessageRequest,
    _current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SendMessageResponse:
    return await service.send_message(body.session_id, body.message, db)
