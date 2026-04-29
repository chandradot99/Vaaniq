from datetime import timedelta

from pydantic_settings import BaseSettings, SettingsConfigDict

from naaviq.server.auth.constants import (
    DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES,
    DEFAULT_JWT_ALGORITHM,
    DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS,
)
from naaviq.server.core.env import ENV_FILE


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    secret_key: str
    jwt_algorithm: str = DEFAULT_JWT_ALGORITHM
    access_token_expire_minutes: int = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES
    refresh_token_expire_days: int = DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS

    @property
    def access_token_expire(self) -> timedelta:
        return timedelta(minutes=self.access_token_expire_minutes)

    @property
    def refresh_token_expire(self) -> timedelta:
        return timedelta(days=self.refresh_token_expire_days)


auth_settings = AuthConfig()
