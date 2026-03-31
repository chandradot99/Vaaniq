from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.database import get_db
from vaaniq.server.core.security import decode_token
from vaaniq.server.auth.models import User
from vaaniq.server.auth.repository import UserRepository
from vaaniq.server.auth.exceptions import InvalidToken

bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, str]:
    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise InvalidToken()
    if payload.get("type") != "access":
        raise InvalidToken("Invalid token type")

    repo = UserRepository(db)
    user = await repo.get_by_id(payload["sub"])
    if not user:
        raise InvalidToken("User not found")

    org_id = await repo.get_org_id(user.id)
    return user, org_id
