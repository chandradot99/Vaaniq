"""SessionRepository — persistence for chat session metadata.

The LangGraph checkpointer handles conversation state (messages, collected
fields, etc.). This repository handles the sessions table — lifecycle status,
transcript snapshot, and post-session analytics written when a session ends.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaaniq.server.models.session import Session


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        org_id: str,
        agent_id: str,
        channel: str = "chat",
        user_id: str = "",
        meta: dict | None = None,
    ) -> Session:
        session = Session(
            id=str(uuid.uuid4()),
            org_id=org_id,
            agent_id=agent_id,
            channel=channel,
            user_id=user_id,
            status="active",
            transcript=[],
            tool_calls=[],
            meta=meta or {},
        )
        self.db.add(session)
        return session

    async def get(self, session_id: str) -> Session | None:
        result = await self.db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def mark_ended(
        self,
        session_id: str,
        transcript: list | None = None,
        tool_calls: list | None = None,
        duration_seconds: int | None = None,
        sentiment: str | None = None,
        summary: str | None = None,
    ) -> None:
        session = await self.get(session_id)
        if not session:
            return
        session.status = "ended"
        session.ended_at = datetime.now(timezone.utc)
        if transcript is not None:
            session.transcript = transcript
        if tool_calls is not None:
            session.tool_calls = tool_calls
        if duration_seconds is not None:
            session.duration_seconds = duration_seconds
        if sentiment is not None:
            session.sentiment = sentiment
        if summary is not None:
            session.summary = summary
