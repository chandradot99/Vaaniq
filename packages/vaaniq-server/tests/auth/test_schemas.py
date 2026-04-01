"""Unit tests for auth schema validation — no DB required."""
import pytest
from pydantic import ValidationError
from vaaniq.server.auth.schemas import RegisterRequest


def _valid_payload(**overrides) -> dict:
    return {
        "email": "user@example.com",
        "name": "Test User",
        "password": "Password1",
        "org_name": "Acme",
        **overrides,
    }


def test_register_valid():
    req = RegisterRequest(**_valid_payload())
    assert req.email == "user@example.com"


def test_password_too_short():
    with pytest.raises(ValidationError, match="at least 8 characters"):
        RegisterRequest(**_valid_payload(password="Ab1"))


def test_password_no_uppercase():
    with pytest.raises(ValidationError, match="uppercase"):
        RegisterRequest(**_valid_payload(password="password1"))


def test_password_no_digit():
    with pytest.raises(ValidationError, match="digit"):
        RegisterRequest(**_valid_payload(password="Password"))


def test_invalid_email():
    with pytest.raises(ValidationError):
        RegisterRequest(**_valid_payload(email="not-an-email"))
