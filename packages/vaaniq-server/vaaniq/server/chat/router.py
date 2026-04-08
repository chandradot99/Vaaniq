from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.agents.dependencies import valid_agent
from vaaniq.server.agents.models import Agent
from vaaniq.server.auth.dependencies import CurrentUser, get_current_user
from vaaniq.server.chat import service
from vaaniq.server.chat.exceptions import ChatSessionNotFound
from vaaniq.server.chat.repository import SessionRepository
from vaaniq.server.chat.schemas import (
    SendMessageRequest,
    SendMessageResponse,
    SessionDetail,
    SessionEventSchema,
    SessionListResponse,
    SessionSummary,
    SessionTimeline,
    StartChatResponse,
    ToolCallDetail,
    TranscriptMessage,
)
from vaaniq.server.chat.tracing import SessionEventRepository
from vaaniq.server.core.database import get_db

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


@router.get("/agents/{agent_id}/sessions", response_model=SessionListResponse)
async def list_sessions(
    agent_id: str,
    limit: int = 20,
    offset: int = 0,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionListResponse:
    sessions, total = await SessionRepository(db).list_by_agent(
        agent_id=agent_id,
        org_id=current.org_id,
        limit=min(limit, 50),
        offset=offset,
    )
    summaries = [
        SessionSummary(
            id=s.id,
            agent_id=s.agent_id,
            status=s.status,
            had_error=bool((s.meta or {}).get("failed", False)),
            channel=s.channel,
            message_count=len(s.transcript or []),
            tool_call_count=len(s.tool_calls or []),
            duration_seconds=s.duration_seconds,
            sentiment=s.sentiment,
            created_at=s.created_at,
            ended_at=s.ended_at,
        )
        for s in sessions
    ]
    return SessionListResponse(sessions=summaries, total=total)


@router.post("/sessions/{session_id}/abandon", status_code=204)
async def abandon_session(
    session_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Mark an active session as ended when the user closes the chat panel."""
    await service.abandon_session(session_id, current.org_id, db)


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionDetail:
    session = await SessionRepository(db).get(session_id)
    if not session or session.org_id != current.org_id:
        raise ChatSessionNotFound()
    return SessionDetail(
        id=session.id,
        agent_id=session.agent_id,
        status=session.status,
        channel=session.channel,
        duration_seconds=session.duration_seconds,
        sentiment=session.sentiment,
        summary=session.summary,
        meta=session.meta or {},
        transcript=[TranscriptMessage(**m) for m in (session.transcript or [])],
        tool_calls=[ToolCallDetail(**tc) for tc in (session.tool_calls or [])],
        created_at=session.created_at,
        ended_at=session.ended_at,
    )


@router.get("/sessions/{session_id}/events", response_model=SessionTimeline)
async def get_session_events(
    session_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionTimeline:
    """Return the full execution timeline for a session."""
    session = await SessionRepository(db).get(session_id)
    if not session or session.org_id != current.org_id:
        raise ChatSessionNotFound()
    events = await SessionEventRepository(db).list_by_session(session_id)
    event_schemas = [
        SessionEventSchema(
            id=e.id,
            turn=e.turn,
            seq=e.seq,
            event_type=e.event_type,
            name=e.name,
            started_at=e.started_at,
            ended_at=e.ended_at,
            duration_ms=e.duration_ms,
            status=e.status,
            data=e.data or {},
            error=e.error,
        )
        for e in events
    ]
    turns = {e.turn for e in events}
    total_llm_tokens = sum(
        (e.data or {}).get("total_tokens", 0)
        for e in events
        if e.event_type == "llm"
    )
    total_duration_ms = sum(e.duration_ms or 0 for e in events if e.event_type == "node")
    return SessionTimeline(
        session_id=session_id,
        events=event_schemas,
        total_turns=len(turns),
        total_llm_tokens=total_llm_tokens,
        total_duration_ms=total_duration_ms,
    )


@router.post("/stream")
async def stream_message(
    body: SendMessageRequest,
    _current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream agent response tokens as Server-Sent Events.

    Event format: each line is `data: <json>\\n\\n`
    Event types: token | node_start | node_end | human_review | ended | error
    """
    return StreamingResponse(
        service.stream_message(body.session_id, body.message, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering for SSE
        },
    )
