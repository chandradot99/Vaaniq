from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from vaaniq.server.auth.config import auth_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, extra: Optional[dict[str, Any]] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=auth_settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire, "type": "access"}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, auth_settings.secret_key, algorithm=auth_settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + auth_settings.refresh_token_expire
    return jwt.encode(
        {"sub": subject, "exp": expire, "type": "refresh"},
        auth_settings.secret_key,
        algorithm=auth_settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, auth_settings.secret_key, algorithms=[auth_settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
