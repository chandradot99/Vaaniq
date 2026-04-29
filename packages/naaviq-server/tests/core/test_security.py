"""Unit tests for core/security.py — no DB required."""
import pytest
from jose import jwt
from naaviq.server.auth.config import auth_settings
from naaviq.server.core.security import (
    create_access_token,
    decode_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_hash_password_returns_hash():
    hashed = hash_password("Password1")
    assert hashed != "Password1"
    assert len(hashed) > 20


def test_verify_password_correct():
    hashed = hash_password("Password1")
    assert verify_password("Password1", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("Password1")
    assert verify_password("WrongPass1", hashed) is False


def test_create_access_token_payload():
    token = create_access_token("user-123", "org-456", "owner")
    payload = jwt.decode(token, auth_settings.secret_key, algorithms=[auth_settings.jwt_algorithm])

    assert payload["sub"] == "user-123"
    assert payload["org_id"] == "org-456"
    assert payload["role"] == "owner"
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload


def test_decode_token_valid():
    token = create_access_token("user-123", "org-456", "member")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"


def test_decode_token_invalid():
    with pytest.raises(ValueError, match="Invalid token"):
        decode_token("not.a.valid.token")


def test_decode_token_tampered():
    token = create_access_token("user-123", "org-456", "owner")
    tampered = token[:-5] + "xxxxx"
    with pytest.raises(ValueError, match="Invalid token"):
        decode_token(tampered)


def test_hash_token_is_deterministic():
    assert hash_token("abc") == hash_token("abc")


def test_hash_token_different_inputs():
    assert hash_token("abc") != hash_token("xyz")


def test_generate_refresh_token_unique():
    tokens = {generate_refresh_token() for _ in range(10)}
    assert len(tokens) == 10  # all unique


def test_generate_refresh_token_length():
    token = generate_refresh_token()
    assert len(token) >= 32
