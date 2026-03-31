from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from vaaniq.server.auth.models import User, OrgMember


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_org_id(self, user_id: str) -> str:
        result = await self.db.execute(
            select(OrgMember).where(OrgMember.user_id == user_id)
        )
        member = result.scalar_one_or_none()
        return member.org_id if member else ""
