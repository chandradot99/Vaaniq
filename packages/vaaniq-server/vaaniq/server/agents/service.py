from typing import Any
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.agents.models import Agent
from vaaniq.server.agents.repository import AgentRepository
from vaaniq.server.agents.schemas import (
    AgentResponse,
    CreateAgentRequest,
    UpdateAgentRequest,
)
from vaaniq.server.agents.exceptions import AgentNotFound, AgentAccessDenied

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

        fields: dict[str, Any] = {
            k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None
        }

        # If system_prompt changed and no custom graph has been set, regenerate default graph
        if "system_prompt" in fields and agent.simple_mode:
            fields["graph_config"] = _default_graph(fields["system_prompt"])

        if fields:
            await self.repo.update(agent_id, **fields)
            await self.db.commit()
            await self.db.refresh(agent)

        log.info("agent_updated", org_id=org_id, agent_id=agent_id)
        return _to_response(agent)

    async def update_graph(self, agent_id: str, org_id: str, graph_config: dict) -> AgentResponse:
        agent = await self.repo.get_by_id(agent_id)
        if not agent:
            raise AgentNotFound()
        if agent.org_id != org_id:
            raise AgentAccessDenied()

        await self.repo.update(agent_id, graph_config=graph_config, simple_mode=False)
        await self.db.commit()
        # expire_on_commit=False means commit does NOT clear the session identity map.
        # Refresh forces a SELECT to get the just-written graph_config instead of the
        # stale pre-update values still sitting in the ORM cache.
        await self.db.refresh(agent)

        log.info("agent_graph_updated", org_id=org_id, agent_id=agent_id)
        return _to_response(agent)

    async def delete(self, agent_id: str, org_id: str) -> None:
        agent = await self.repo.get_by_id(agent_id)
        if not agent:
            raise AgentNotFound()
        if agent.org_id != org_id:
            raise AgentAccessDenied()

        await self.repo.soft_delete(agent_id)
        await self.db.commit()

        log.info("agent_deleted", org_id=org_id, agent_id=agent_id)
