from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from vaaniq.server.core.database import get_db
from vaaniq.server.core.security import decode_token
from vaaniq.server.auth.models import User, Organization
from vaaniq.server.auth.repository import UserRepository
from vaaniq.server.auth.service import AuthService
from vaaniq.server.auth.dependencies import get_current_user
from vaaniq.server.auth.exceptions import EmailAlreadyExists, InvalidCredentials, InvalidToken
from vaaniq.server.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from fastapi import status

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    if await UserRepository(db).get_by_email(body.email):
        raise EmailAlreadyExists()
    return await AuthService(db).register(body)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        tokens, _ = await AuthService(db).login(body.email, body.password)
        return tokens
    except ValueError:
        raise InvalidCredentials()


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        payload = decode_token(body.refresh_token)
    except ValueError:
        raise InvalidToken("Invalid refresh token")
    if payload.get("type") != "refresh":
        raise InvalidToken("Invalid token type")
    try:
        return await AuthService(db).refresh(payload["sub"])
    except ValueError:
        raise InvalidToken("User not found")


@router.get("/me", response_model=UserResponse)
async def me(
    current: tuple[User, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user, org_id = current
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        org_id=org_id,
        org_name=org.name if org else "",
    )
