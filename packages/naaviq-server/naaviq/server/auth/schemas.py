from pydantic import EmailStr, field_validator

from naaviq.server.core.schemas import CustomModel


class RegisterRequest(CustomModel):
    email: EmailStr
    name: str
    password: str
    org_name: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(CustomModel):
    email: EmailStr
    password: str


class RefreshRequest(CustomModel):
    refresh_token: str


class LogoutRequest(CustomModel):
    refresh_token: str


class TokenResponse(CustomModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    org_id: str
    role: str


class UserResponse(CustomModel):
    id: str
    email: str
    name: str
    org_id: str
    org_name: str
    role: str
