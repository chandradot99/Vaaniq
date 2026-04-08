"""SessionRepository — persistence for chat session metadata.

The LangGraph checkpointer handles conversation state (messages, collected
fields, etc.). This repository handles the sessions table — lifecycle status,
transcript snapshot, and post-session analytics written when a session ends.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
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

    async def update_transcript(
        self,
        session_id: str,
        transcript: list,
        tool_calls: list,
        meta: dict | None = None,
    ) -> None:
        """Write transcript + tool_calls after every turn so the Sessions tab is always fresh."""
        session = await self.get(session_id)
        if not session:
            return
        session.transcript = transcript
        session.tool_calls = tool_calls
        if meta:
            session.meta = {**(session.meta or {}), **meta}

    async def mark_ended(
        self,
        session_id: str,
        transcript: list | None = None,
        tool_calls: list | None = None,
        duration_seconds: int | None = None,
        sentiment: str | None = None,
        summary: str | None = None,
        meta: dict | None = None,
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
        if meta:
            session.meta = {**(session.meta or {}), **meta}

    async def list_by_agent(
        self,
        agent_id: str,
        org_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Session], int]:
        base = select(Session).where(
            Session.agent_id == agent_id,
            Session.org_id == org_id,
        )
        total_result = await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = total_result.scalar_one()
        result = await self.db.execute(
            base.order_by(Session.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total
