import json
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from naaviq.server.agents.exceptions import AgentAccessDenied, AgentNotFound
from naaviq.server.agents.models import Agent
from naaviq.server.agents.repository import AgentRepository
from naaviq.server.agents.schemas import (
    AgentResponse,
    CreateAgentRequest,
    UpdateAgentRequest,
    UpdateVoiceConfigRequest,
    VoicePreviewResponse,
)
from naaviq.server.voice.exceptions import AgentNotConfigured

log = structlog.get_logger()


def _default_graph(system_prompt: str) -> dict:
    """Generate the default multi-turn graph for new agents.

    Layout (left-to-right):
      [start] → [inbound_message] → [llm_response] → [inbound_message]  (loop)
      [end_session] placed on canvas, disconnected — user wires it when ready.

    start holds the system message and optional greeting.
    inbound_message interrupts and waits for each user turn.
    """
    return {
        "entry_point": "start",
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "label": "Start",
                "position": {"x": 100, "y": 200},
                "config": {
                    "system_message": system_prompt or "You are a helpful assistant.",
                    "greeting": "Hello! How can I help you today?",
                },
            },
            {
                "id": "inbound_message",
                "type": "inbound_message",
                "label": "Inbound Message",
                "position": {"x": 400, "y": 200},
                "config": {},
            },
            {
                "id": "llm_response",
                "type": "llm_response",
                "label": "LLM Response",
                "position": {"x": 700, "y": 200},
                "config": {
                    "instructions": "",
                    "tools": [],
                    "rag_enabled": False,
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "inbound_message"},
            {"id": "e2", "source": "inbound_message", "target": "llm_response"},
            {
                "id": "e3",
                "source": "llm_response",
                "target": "inbound_message",
                "goto": True,
                "goto_node_position": {"x": 1000, "y": 200},
            },
        ],
    }


def _to_response(agent: Agent) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        org_id=agent.org_id,
        name=agent.name,
        system_prompt=agent.system_prompt,
        voice_id=agent.voice_id,
        voice_config=agent.voice_config,
        language=agent.language,
        simple_mode=agent.simple_mode,
        graph_config=agent.graph_config,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


class AgentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AgentRepository(db)

    async def create(self, org_id: str, data: CreateAgentRequest) -> AgentResponse:
        graph_config = data.graph_config
        if graph_config is None:
            graph_config = _default_graph(data.system_prompt)

        agent = await self.repo.create(
            org_id=org_id,
            name=data.name,
            system_prompt=data.system_prompt,
            voice_id=data.voice_id,
            language=data.language,
            simple_mode=data.simple_mode,
            graph_config=graph_config,
        )
        await self.db.commit()
        await self.db.refresh(agent)

        log.info("agent_created", org_id=org_id, agent_id=agent.id)
        return _to_response(agent)

    async def list(self, org_id: str) -> list[AgentResponse]:
        agents = await self.repo.list_by_org(org_id)
        return [_to_response(a) for a in agents]

    async def get(self, agent_id: str, org_id: str) -> AgentResponse:
        agent = await self.repo.get_by_id(agent_id)
        if not agent:
            raise AgentNotFound()
        if agent.org_id != org_id:
            raise AgentAccessDenied()
        return _to_response(agent)

    async def update(self, agent_id: str, org_id: str, data: UpdateAgentRequest) -> AgentResponse:
        agent = await self.repo.get_by_id(agent_id)
        if not agent:
            raise AgentNotFound()
        if agent.org_id != org_id:
            raise AgentAccessDenied()

        dumped = data.model_dump(exclude_unset=True)
        fields: dict[str, Any] = {k: v for k, v in dumped.items() if v is not None}

        # If system_prompt changed and no custom graph has been set, regenerate default graph
        if "system_prompt" in fields and agent.simple_mode:
            fields["graph_config"] = _default_graph(fields["system_prompt"])

        if fields:
            await self.repo.update(agent_id, **fields)
            await self.db.commit()
            await self.db.refresh(agent)

        log.info("agent_updated", org_id=org_id, agent_id=agent_id)
        return _to_response(agent)

    async def update_voice_config(
        self, agent_id: str, org_id: str, data: UpdateVoiceConfigRequest
    ) -> AgentResponse:
        agent = await self.repo.get_by_id(agent_id)
        if not agent:
            raise AgentNotFound()
        if agent.org_id != org_id:
            raise AgentAccessDenied()

        voice_config = data.voice_config.model_dump() if data.voice_config else None
        await self.repo.update(agent_id, voice_config=voice_config)
        await self.db.commit()
        await self.db.refresh(agent)

        log.info("agent_voice_config_updated", org_id=org_id, agent_id=agent_id)
        return _to_response(agent)

    async def update_graph(self, agent_id: str, org_id: str, graph_config: dict) -> AgentResponse:
        agent = await self.repo.get_by_id(agent_id)
        if not agent:
            raise AgentNotFound()
        if agent.org_id != org_id:
            raise AgentAccessDenied()

        new_version = (agent.graph_version or 1) + 1
        await self.repo.update(
            agent_id,
            graph_config=graph_config,
            graph_version=new_version,
            simple_mode=False,
        )
        await self.db.commit()
        # expire_on_commit=False means commit does NOT clear the session identity map.
        # Refresh forces a SELECT to get the just-written graph_config instead of the
        # stale pre-update values still sitting in the ORM cache.
        await self.db.refresh(agent)

        log.info("agent_graph_updated", org_id=org_id, agent_id=agent_id, graph_version=new_version)
        return _to_response(agent)

    async def start_voice_preview(
        self,
        agent: Agent,
        user_identity: str,
    ) -> VoicePreviewResponse:
        """
        Start a browser-based voice preview session for an agent.

        Creates a DB session, a LiveKit room, dispatches the voice worker,
        and returns a participant token so the browser can join immediately.

        Args:
            agent:         The validated Agent ORM object.
            user_identity: A stable identifier for the previewing user (e.g. user ID).
                           Used as the LiveKit participant identity.
        """
        if not agent.graph_config:
            raise AgentNotConfigured(str(agent.id))

        from naaviq.server.core.config import settings

        livekit_url: str = getattr(settings, "livekit_url", "")
        livekit_api_key: str = getattr(settings, "livekit_api_key", "")
        livekit_api_secret: str = getattr(settings, "livekit_api_secret", "")

        # ── 1. Create preview session in DB ───────────────────────────────────
        session_id = str(uuid.uuid4())
        from naaviq.server.models.session import ChannelEnum, Session, SessionStatus

        session = Session(
            id=session_id,
            org_id=agent.org_id,
            agent_id=agent.id,
            channel=ChannelEnum.voice,
            user_id=f"preview:{user_identity}",
            status=SessionStatus.active,
            meta={"preview": True, "previewed_by": user_identity},
        )
        self.db.add(session)
        await self.db.commit()

        log.info("voice_preview_session_created", session_id=session_id, agent_id=agent.id)

        # Room name = session_id so the worker can load context from DB.
        room_name = session_id

        # ── 2. Create LiveKit room + dispatch worker ───────────────────────────
        if livekit_api_key and livekit_api_secret:
            try:
                from livekit.api import (
                    CreateAgentDispatchRequest,
                    CreateRoomRequest,
                    LiveKitAPI,
                )

                async with LiveKitAPI(
                    url=livekit_url,
                    api_key=livekit_api_key,
                    api_secret=livekit_api_secret,
                ) as lk:
                    await lk.room.create_room(
                        CreateRoomRequest(
                            name=room_name,
                            metadata=json.dumps({"session_id": session_id}),
                            empty_timeout=600,   # 10 min — clean up if browser never connects
                            max_participants=5,
                        )
                    )
                    # Explicit dispatch — tells the worker to join this specific room.
                    # The agent_name must match what the worker registers as.
                    await lk.agent_dispatch.create_dispatch(
                        CreateAgentDispatchRequest(
                            agent_name="naaviq-voice",
                            room=room_name,
                        )
                    )

                log.info("voice_preview_room_created", session_id=session_id, room=room_name)
            except Exception as exc:
                log.warning(
                    "voice_preview_room_create_failed",
                    session_id=session_id,
                    error=str(exc),
                )
        else:
            log.warning("voice_preview_livekit_not_configured", session_id=session_id)

        # ── 3. Generate participant token ─────────────────────────────────────
        token = _make_livekit_token(
            api_key=livekit_api_key,
            api_secret=livekit_api_secret,
            room_name=room_name,
            identity=f"preview-{user_identity}",
            display_name="Preview User",
        )

        return VoicePreviewResponse(
            session_id=session_id,
            room_name=room_name,
            token=token,
            livekit_url=livekit_url,
        )

    async def delete(self, agent_id: str, org_id: str) -> None:
        agent = await self.repo.get_by_id(agent_id)
        if not agent:
            raise AgentNotFound()
        if agent.org_id != org_id:
            raise AgentAccessDenied()

        await self.repo.soft_delete(agent_id)
        await self.db.commit()

        log.info("agent_deleted", org_id=org_id, agent_id=agent_id)


def _make_livekit_token(
    *,
    api_key: str,
    api_secret: str,
    room_name: str,
    identity: str,
    display_name: str,
) -> str:
    """
    Generate a short-lived LiveKit participant token for browser access.

    The token grants publish + subscribe rights in the specified room only.
    TTL is 1 hour — enough for an agent preview session.
    """
    if not api_key or not api_secret:
        # Return an empty token when LiveKit is not configured (e.g. unit tests).
        return ""

    from livekit.api import AccessToken, VideoGrants

    token = (
        AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity(identity)
        .with_name(display_name)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )
    return token
