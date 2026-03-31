import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from vaaniq.server.core.database import get_db
from vaaniq.server.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from vaaniq.server.models.user import User
from vaaniq.server.models.organization import Organization, OrgMember
from vaaniq.server.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])
bearer = HTTPBearer()
log = structlog.get_logger()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, str]:
    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    result = await db.execute(select(User).where(User.id == payload["sub"], User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    member = await db.execute(select(OrgMember).where(OrgMember.user_id == user.id))
    org_member = member.scalar_one_or_none()
    org_id = org_member.org_id if org_member else ""
    return user, org_id


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    org = Organization(id=str(uuid.uuid4()), name=body.org_name, owner_id=user.id)
    db.add(org)
    await db.flush()

    db.add(OrgMember(org_id=org.id, user_id=user.id, role="owner"))
    await db.commit()

    log.info("user_registered", user_id=user.id, org_id=org.id)
    return TokenResponse(
        access_token=create_access_token(user.id, {"org_id": org.id}),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    member = await db.execute(select(OrgMember).where(OrgMember.user_id == user.id))
    org_member = member.scalar_one_or_none()
    org_id = org_member.org_id if org_member else ""

    log.info("user_login", user_id=user.id, org_id=org_id)
    return TokenResponse(
        access_token=create_access_token(user.id, {"org_id": org_id}),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        payload = decode_token(body.refresh_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    result = await db.execute(select(User).where(User.id == payload["sub"], User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    member = await db.execute(select(OrgMember).where(OrgMember.user_id == user.id))
    org_member = member.scalar_one_or_none()
    org_id = org_member.org_id if org_member else ""

    return TokenResponse(
        access_token=create_access_token(user.id, {"org_id": org_id}),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
async def me(
    current: tuple[User, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user, org_id = current
    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_result.scalar_one_or_none()
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        org_id=org_id,
        org_name=org.name if org else "",
    )
