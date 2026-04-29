from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from naaviq.server.auth.config import auth_settings
from naaviq.server.auth.constants import OrgRole
from naaviq.server.auth.exceptions import InvalidCredentials, InvalidToken
from naaviq.server.auth.models import User
from naaviq.server.auth.repository import AuthRepository
from naaviq.server.auth.schemas import RegisterRequest, TokenResponse
from naaviq.server.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)

log = structlog.get_logger()


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AuthRepository(db)

    async def register(self, data: RegisterRequest) -> TokenResponse:
        user = await self.repo.create_user(data.email, data.name)
        await self.repo.create_email_identity(user.id, hash_password(data.password))
        org = await self.repo.create_org(data.org_name, user.id)
        await self.repo.add_org_member(org.id, user.id, OrgRole.OWNER)

        tokens = await self._issue_tokens(user, org.id, OrgRole.OWNER)
        await self.db.commit()

        log.info("user_registered", user_id=user.id, org_id=org.id)
        return tokens

    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self.repo.get_user_by_email(email)
        if not user:
            raise InvalidCredentials()

        identity = await self.repo.get_email_identity(user.id)
        if not identity or not identity.password_hash:
            raise InvalidCredentials()
        if not verify_password(password, identity.password_hash):
            raise InvalidCredentials()

        # Prefer the org where user is owner; fall back to first membership
        memberships = await self.repo.get_user_memberships(user.id)
        if not memberships:
            raise InvalidCredentials()

        member, org = next(
            ((m, o) for m, o in memberships if m.role == OrgRole.OWNER),
            memberships[0],
        )

        await self.repo.touch_identity(identity.id)
        tokens = await self._issue_tokens(user, org.id, member.role)
        await self.db.commit()

        log.info("user_login", user_id=user.id, org_id=org.id)
        return tokens

    async def refresh(self, raw_token: str) -> TokenResponse:
        stored = await self.repo.get_refresh_token(hash_token(raw_token))

        if not stored:
            raise InvalidToken("Refresh token not found")
        if stored.revoked_at is not None:
            raise InvalidToken("Refresh token has been revoked")
        if stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise InvalidToken("Refresh token has expired")

        user = await self.repo.get_user_by_id(stored.user_id)
        if not user:
            raise InvalidToken("User not found")

        memberships = await self.repo.get_user_memberships(user.id)
        pair = next(((m, o) for m, o in memberships if o.id == stored.org_id), None)
        if not pair:
            raise InvalidToken("Org membership not found")
        member, org = pair

        # Rotate: revoke old token, issue new pair
        await self.repo.revoke_refresh_token(stored.id)
        tokens = await self._issue_tokens(user, org.id, member.role)
        await self.db.commit()

        return tokens

    async def logout(self, raw_token: str) -> None:
        stored = await self.repo.get_refresh_token(hash_token(raw_token))
        if stored and stored.revoked_at is None:
            await self.repo.revoke_refresh_token(stored.id)
            await self.db.commit()

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _issue_tokens(self, user: User, org_id: str, role: str) -> TokenResponse:
        access_token = create_access_token(user.id, org_id, role)

        raw_refresh = generate_refresh_token()
        expires_at = datetime.now(timezone.utc) + auth_settings.refresh_token_expire
        await self.repo.create_refresh_token(user.id, org_id, hash_token(raw_refresh), expires_at)

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            org_id=org_id,
            role=role,
        )
