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
from vaaniq.server.agents.constants import DEFAULT_FAREWELL_MESSAGE
from vaaniq.server.agents.exceptions import AgentNotFound, AgentAccessDenied

log = structlog.get_logger()


def _simple_graph(system_prompt: str) -> dict:
    """Auto-generate a minimal graph for simple_mode agents."""
    return {
        "entry_point": "llm_response",
        "nodes": [
            {
                "id": "llm_response",
                "type": "llm_response",
                "config": {
                    "instructions": system_prompt or "You are a helpful assistant.",
                    "tools": [],
                    "rag_enabled": False,
                },
            },
            {
                "id": "end",
                "type": "end_session",
                "config": {"farewell_message": DEFAULT_FAREWELL_MESSAGE},
            },
        ],
        "edges": [
            {"id": "e1", "source": "llm_response", "target": "end"},
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
        if data.simple_mode and graph_config is None:
            graph_config = _simple_graph(data.system_prompt)

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

        # If system_prompt changed and agent is in simple_mode, regenerate graph
        if "system_prompt" in fields and agent.simple_mode:
            fields["graph_config"] = _simple_graph(fields["system_prompt"])

        if fields:
            await self.repo.update(agent_id, **fields)
            await self.db.commit()
            agent = await self.repo.get_by_id(agent_id)

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
        agent = await self.repo.get_by_id(agent_id)

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
