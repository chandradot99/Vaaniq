"""
Repository for phone_numbers table CRUD operations.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from naaviq.server.voice.models import PhoneNumber


class PhoneNumberRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        org_id: str,
        agent_id: str,
        number: str,
        provider: str = "twilio",
        sid: str = "",
        friendly_name: str | None = None,
    ) -> PhoneNumber:
        phone = PhoneNumber(
            id=str(uuid.uuid4()),
            org_id=org_id,
            agent_id=agent_id,
            number=number,
            provider=provider,
            sid=sid,
            friendly_name=friendly_name,
        )
        self.db.add(phone)
        await self.db.flush()
        return phone

    async def get_by_id(self, number_id: str) -> PhoneNumber | None:
        """Look up an active phone number record by primary key."""
        result = await self.db.execute(
            select(PhoneNumber).where(
                PhoneNumber.id == number_id,
                PhoneNumber.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_number(self, number: str) -> PhoneNumber | None:
        """Look up an active phone number record by E.164 number."""
        result = await self.db.execute(
            select(PhoneNumber).where(
                PhoneNumber.number == number,
                PhoneNumber.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_org(self, org_id: str) -> list[PhoneNumber]:
        result = await self.db.execute(
            select(PhoneNumber)
            .where(PhoneNumber.org_id == org_id, PhoneNumber.deleted_at.is_(None))
            .order_by(PhoneNumber.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_agent(self, agent_id: str) -> list[PhoneNumber]:
        result = await self.db.execute(
            select(PhoneNumber)
            .where(PhoneNumber.agent_id == agent_id, PhoneNumber.deleted_at.is_(None))
            .order_by(PhoneNumber.created_at.desc())
        )
        return list(result.scalars().all())

    async def reassign(self, number_id: str, agent_id: str) -> None:
        """Move a phone number to a different agent within the same org."""
        await self.db.execute(
            update(PhoneNumber)
            .where(PhoneNumber.id == number_id)
            .values(agent_id=agent_id)
        )

    async def get_by_friendly_name(self, org_id: str, friendly_name: str) -> "PhoneNumber | None":
        """Check if a friendly_name is already taken within this org (active rows only)."""
        result = await self.db.execute(
            select(PhoneNumber).where(
                PhoneNumber.org_id == org_id,
                PhoneNumber.friendly_name == friendly_name,
                PhoneNumber.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_friendly_name(self, number_id: str, friendly_name: str | None) -> None:
        await self.db.execute(
            update(PhoneNumber)
            .where(PhoneNumber.id == number_id)
            .values(friendly_name=friendly_name)
        )

    async def update_voice_config(self, number_id: str, voice_config: dict | None) -> None:
        await self.db.execute(
            update(PhoneNumber)
            .where(PhoneNumber.id == number_id)
            .values(voice_config=voice_config)
        )

    async def soft_delete(self, number_id: str) -> None:
        await self.db.execute(
            update(PhoneNumber)
            .where(PhoneNumber.id == number_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )
