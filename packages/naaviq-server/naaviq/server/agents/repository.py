import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from naaviq.server.agents.models import Agent


class AgentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, org_id: str, name: str, **kwargs: Any) -> Agent:
        agent = Agent(
            id=str(uuid.uuid4()),
            org_id=org_id,
            name=name,
            **kwargs,
        )
        self.db.add(agent)
        await self.db.flush()
        return agent

    async def get_by_id(self, agent_id: str) -> Agent | None:
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_by_org(self, org_id: str) -> list[Agent]:
        result = await self.db.execute(
            select(Agent)
            .where(Agent.org_id == org_id, Agent.deleted_at.is_(None))
            .order_by(Agent.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, agent_id: str, **fields: Any) -> None:
        await self.db.execute(
            update(Agent)
            .where(Agent.id == agent_id)
            .values(**fields, updated_at=datetime.now(timezone.utc))
        )

    async def list_all_active(self) -> list[Agent]:
        """Return all non-deleted agents across all orgs — used for startup graph cache prewarm."""
        result = await self.db.execute(
            select(Agent).where(Agent.deleted_at.is_(None), Agent.graph_config.isnot(None))
        )
        return list(result.scalars().all())

    async def get_first_active(self) -> Agent | None:
        """Fallback — returns the most recently created non-deleted agent."""
        result = await self.db.execute(
            select(Agent)
            .where(Agent.deleted_at.is_(None))
            .order_by(Agent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_phone_number(self, phone_number: str) -> Agent | None:
        """
        Look up an agent by the Twilio number that received the call.
        Requires the phone_numbers table (added in Step 9).
        Returns None until that migration runs — callers fall back to get_first_active().
        """
        try:
            from sqlalchemy import text
            result = await self.db.execute(
                text(
                    "SELECT a.* FROM agents a "
                    "JOIN phone_numbers pn ON pn.agent_id = a.id "
                    "WHERE pn.number = :number AND pn.deleted_at IS NULL AND a.deleted_at IS NULL "
                    "LIMIT 1"
                ),
                {"number": phone_number},
            )
            row = result.mappings().first()
            if row:
                return await self.get_by_id(str(row["id"]))
            return None
        except Exception:
            # phone_numbers table doesn't exist yet — safe to return None
            return None

    async def soft_delete(self, agent_id: str) -> None:
        await self.db.execute(
            update(Agent)
            .where(Agent.id == agent_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )
