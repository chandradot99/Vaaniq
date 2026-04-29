import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from naaviq.server.agents.repository import AgentRepository
from naaviq.server.models.session import Session, SessionStatus
from naaviq.server.webhooks.repository import SessionRepository

log = structlog.get_logger()


class VoiceWebhookService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.agent_repo = AgentRepository(db)
        self.session_repo = SessionRepository(db)

    async def handle_inbound(
        self, call_sid: str, from_number: str, to_number: str
    ) -> str | None:
        """
        Handle an inbound call from Twilio.

        1. Look up which agent owns this Twilio number.
        2. Create a session row (channel='voice', status='active').
        3. Return session_id — the caller constructs the TwiML with the
           correct voice server WebSocket URL.

        Returns None if no agent is configured for this number (caller
        should return a hangup TwiML response).
        """
        log.info("voice_inbound", call_sid=call_sid, from_number=from_number, to_number=to_number)

        agent = await self.agent_repo.get_by_phone_number(to_number)
        if not agent:
            agent = await self.agent_repo.get_first_active()

        if not agent:
            log.warning("no_agent_for_number", to_number=to_number)
            return None

        session_id = str(uuid.uuid4())
        session = Session(
            id=session_id,
            org_id=str(agent.org_id),
            agent_id=str(agent.id),
            channel="voice",
            user_id=from_number,
            status=SessionStatus.active,
            meta={
                "call_sid": call_sid,
                "from": from_number,
                "to": to_number,
            },
        )
        self.db.add(session)
        await self.db.commit()

        log.info("voice_session_created", session_id=session_id, agent_id=str(agent.id), call_sid=call_sid)
        return session_id

    async def handle_status(
        self, call_sid: str, call_status: str, call_duration: str
    ) -> tuple[str, str] | None:
        """
        Handle Twilio call status callback.
        Updates session duration and marks it ended on terminal statuses.

        Returns (session_id, org_id) when a terminal status is received so the
        caller can schedule post-call finalization as a background task.
        Returns None for non-terminal status transitions.
        """
        log.info("voice_status", call_sid=call_sid, status=call_status, duration=call_duration)

        session = await self.session_repo.get_by_call_sid(call_sid)
        if not session:
            log.warning("voice_status_session_not_found", call_sid=call_sid)
            return None

        _TERMINAL = {"completed", "failed", "busy", "no-answer", "canceled"}
        if call_status in _TERMINAL:
            session.status = SessionStatus.ended
            try:
                session.duration_seconds = int(call_duration)
            except ValueError:
                pass
            await self.db.commit()
            return session.id, session.org_id

        await self.db.commit()
        return None

    async def handle_recording(
        self, call_sid: str, recording_url: str, recording_duration: str
    ) -> None:
        """Store the Twilio recording URL on the session."""
        log.info("voice_recording_ready", call_sid=call_sid, recording_url=recording_url)

        session = await self.session_repo.get_by_call_sid(call_sid)
        if not session:
            return

        meta = dict(session.meta or {})
        meta["recording_url"] = recording_url
        meta["recording_duration"] = recording_duration
        session.meta = meta
        await self.db.commit()
