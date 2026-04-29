from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from naaviq.server.models.session import Session


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, session_id: str) -> Session | None:
        result = await self.db.execute(
            select(Session).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_by_call_sid(self, call_sid: str) -> Session | None:
        """Look up a voice session by its Twilio CallSid stored in meta."""
        result = await self.db.execute(
            select(Session).where(
                Session.channel == "voice",
                Session.meta["call_sid"].astext == call_sid,
            )
        )
        return result.scalar_one_or_none()
