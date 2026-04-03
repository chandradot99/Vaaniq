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


def _default_graph(system_prompt: str) -> dict:
    """Generate the default multi-turn graph for new agents.

    Layout (left-to-right):
      [inbound_message] → [llm_response] → [inbound_message]  (conversation loop)
      [end_session] placed on canvas, disconnected — user wires it when ready.

    This is the industry-standard conversational agent pattern: the graph
    loops on inbound_message until the LLM or a branch explicitly ends the
    session. Single-turn (llm_response → end) is just the degenerate case
    of this loop.
    """
    return {
        "entry_point": "inbound_message",
        "nodes": [
            {
                "id": "inbound_message",
                "type": "inbound_message",
                "position": {"x": 100, "y": 200},
                "config": {},
            },
            {
                "id": "llm_response",
                "type": "llm_response",
                "position": {"x": 400, "y": 200},
                "config": {
                    "instructions": system_prompt or "You are a helpful assistant.",
                    "tools": [],
                    "rag_enabled": False,
                },
            },
            {
                "id": "end_session",
                "type": "end_session",
                "position": {"x": 700, "y": 350},
                "config": {"farewell_message": DEFAULT_FAREWELL_MESSAGE},
            },
        ],
        "edges": [
            {"id": "e1", "source": "inbound_message", "target": "llm_response"},
            {"id": "e2", "source": "llm_response", "target": "inbound_message"},
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
