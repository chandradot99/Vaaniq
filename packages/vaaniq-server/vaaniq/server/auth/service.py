import uuid
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
)
from vaaniq.server.auth.models import User, Organization, OrgMember
from vaaniq.server.auth.repository import UserRepository
from vaaniq.server.auth.schemas import RegisterRequest, TokenResponse

log = structlog.get_logger()


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)

    async def register(self, data: RegisterRequest) -> TokenResponse:
        user = User(
            id=str(uuid.uuid4()),
            email=data.email,
            name=data.name,
            password_hash=hash_password(data.password),
        )
        self.db.add(user)
        await self.db.flush()

        org = Organization(id=str(uuid.uuid4()), name=data.org_name, owner_id=user.id)
        self.db.add(org)
        await self.db.flush()

        self.db.add(OrgMember(org_id=org.id, user_id=user.id, role="owner"))
        await self.db.commit()

        log.info("user_registered", user_id=user.id, org_id=org.id)
        return TokenResponse(
            access_token=create_access_token(user.id, {"org_id": org.id}),
            refresh_token=create_refresh_token(user.id),
        )

    async def login(self, email: str, password: str) -> tuple[TokenResponse, str]:
        user = await self.user_repo.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("Invalid credentials")

        org_id = await self.user_repo.get_org_id(user.id)

        log.info("user_login", user_id=user.id, org_id=org_id)
        return TokenResponse(
            access_token=create_access_token(user.id, {"org_id": org_id}),
            refresh_token=create_refresh_token(user.id),
        ), org_id

    async def refresh(self, user_id: str) -> TokenResponse:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        org_id = await self.user_repo.get_org_id(user.id)
        return TokenResponse(
            access_token=create_access_token(user.id, {"org_id": org_id}),
            refresh_token=create_refresh_token(user.id),
        )
