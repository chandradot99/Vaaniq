from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from vaaniq.server.auth.exceptions import InvalidToken
from vaaniq.server.auth.models import User
from vaaniq.server.core.security import decode_token

bearer = HTTPBearer()


@dataclass
class CurrentUser:
    user: User
    org_id: str
    role: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> CurrentUser:
    """
    Decode the Bearer token and return the current user context.
    org_id and role are read from the JWT payload — no extra DB call needed
    since access tokens are short-lived (15 min).
    """
    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise InvalidToken()

    if payload.get("type") != "access":
        raise InvalidToken("Invalid token type")

    user_id = payload.get("sub")
    org_id = payload.get("org_id")
    role = payload.get("role")

    if not user_id or not org_id or not role:
        raise InvalidToken("Malformed token")

    # Construct a lightweight User object from token claims —
    # routes that need full user data should fetch from DB themselves.
    user = User(id=user_id)
    return CurrentUser(user=user, org_id=org_id, role=role)
