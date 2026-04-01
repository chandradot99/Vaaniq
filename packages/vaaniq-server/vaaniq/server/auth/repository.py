import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from vaaniq.server.auth.models import User, Organization, OrgMember, UserIdentity, RefreshToken


class AuthRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── User ──────────────────────────────────────────────────────────────────

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def create_user(self, email: str, name: str) -> User:
        user = User(id=str(uuid.uuid4()), email=email, name=name)
        self.db.add(user)
        await self.db.flush()
        return user

    # ── Identity ──────────────────────────────────────────────────────────────

    async def get_email_identity(self, user_id: str) -> UserIdentity | None:
        result = await self.db.execute(
            select(UserIdentity).where(
                UserIdentity.user_id == user_id,
                UserIdentity.provider == "email",
            )
        )
        return result.scalar_one_or_none()

    async def create_email_identity(self, user_id: str, password_hash: str) -> UserIdentity:
        identity = UserIdentity(
            id=str(uuid.uuid4()),
            user_id=user_id,
            provider="email",
            password_hash=password_hash,
        )
        self.db.add(identity)
        await self.db.flush()
        return identity

    async def touch_identity(self, identity_id: str) -> None:
        """Update last_used_at to now."""
        await self.db.execute(
            update(UserIdentity)
            .where(UserIdentity.id == identity_id)
            .values(last_used_at=datetime.now(timezone.utc))
        )

    # ── Organisation ──────────────────────────────────────────────────────────

    async def create_org(self, name: str, owner_id: str) -> Organization:
        org = Organization(id=str(uuid.uuid4()), name=name, owner_id=owner_id)
        self.db.add(org)
        await self.db.flush()
        return org

    async def get_org_by_id(self, org_id: str) -> Organization | None:
        result = await self.db.execute(
            select(Organization).where(
                Organization.id == org_id,
                Organization.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def add_org_member(self, org_id: str, user_id: str, role: str) -> OrgMember:
        member = OrgMember(id=str(uuid.uuid4()), org_id=org_id, user_id=user_id, role=role)
        self.db.add(member)
        await self.db.flush()
        return member

    async def get_user_memberships(self, user_id: str) -> list[tuple[OrgMember, Organization]]:
        """Return all (member, org) pairs for a user, active orgs only."""
        result = await self.db.execute(
            select(OrgMember, Organization)
            .join(Organization, OrgMember.org_id == Organization.id)
            .where(OrgMember.user_id == user_id, Organization.deleted_at.is_(None))
        )
        return list(result.all())

    # ── Refresh tokens ────────────────────────────────────────────────────────

    async def create_refresh_token(
        self, user_id: str, org_id: str, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        token = RefreshToken(
            id=str(uuid.uuid4()),
            user_id=user_id,
            org_id=org_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.db.add(token)
        await self.db.flush()
        return token

    async def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke_refresh_token(self, token_id: str) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token_id)
            .values(revoked_at=datetime.now(timezone.utc))
        )
