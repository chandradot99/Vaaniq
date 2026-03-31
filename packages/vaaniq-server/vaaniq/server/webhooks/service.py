import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.models.session import Session
from vaaniq.server.agents.repository import AgentRepository
from vaaniq.server.webhooks.repository import SessionRepository
from vaaniq.server.webhooks.constants import ELEVENLABS_STREAM_URL

log = structlog.get_logger()


class TwilioService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.agent_repo = AgentRepository(db)
        self.session_repo = SessionRepository(db)

    async def handle_inbound(
        self, call_sid: str, from_number: str, to_number: str
    ) -> str:
        """Handle inbound call. Returns TwiML response string."""
        log.info("twilio_inbound", call_sid=call_sid, from_number=from_number, to_number=to_number)

        # Sprint 1: use first active agent — Sprint 2 will look up by phone number
        agent = await self.agent_repo.get_first_active()

        if not agent:
            return "<Response><Say>No agent configured. Goodbye.</Say><Hangup/></Response>"

        session = Session(
            id=call_sid,
            org_id=agent.org_id,
            agent_id=agent.id,
            channel="voice",
            user_id=from_number,
        )
        self.db.add(session)
        await self.db.commit()

        elevenlabs_agent_id = agent.voice_id or ""
        log.info("call_connected_to_elevenlabs", call_sid=call_sid, agent_id=agent.id, org_id=agent.org_id)

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ELEVENLABS_STREAM_URL}?agent_id={elevenlabs_agent_id}" />
  </Connect>
</Response>"""

    async def handle_status(self, call_sid: str, call_status: str, call_duration: str) -> None:
        """Handle call status callback. Updates session duration."""
        log.info("twilio_status", call_sid=call_sid, status=call_status, duration=call_duration)

        session = await self.session_repo.get_by_id(call_sid)
        if session:
            try:
                session.duration_seconds = int(call_duration)
            except ValueError:
                pass
            await self.db.commit()
