from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.auth.dependencies import CurrentUser, get_current_user
from vaaniq.server.auth.exceptions import EmailAlreadyExists
from vaaniq.server.auth.repository import AuthRepository
from vaaniq.server.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from vaaniq.server.auth.service import AuthService
from vaaniq.server.core.database import get_db

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    if await AuthRepository(db).get_user_by_email(body.email):
        raise EmailAlreadyExists()
    return await AuthService(db).register(body)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    return await AuthService(db).login(body.email, body.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    return await AuthService(db).refresh(body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, db: AsyncSession = Depends(get_db)) -> None:
    await AuthService(db).logout(body.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    repo = AuthRepository(db)
    user = await repo.get_user_by_id(current.user.id)
    org = await repo.get_org_by_id(current.org_id)
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        org_id=current.org_id,
        org_name=org.name if org else "",
        role=current.role,
    )
