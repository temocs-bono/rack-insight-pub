"""Unit tests for password hashing and JWT round-trips."""
import uuid

import pytest

from auth.security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("s3cret-password")
    assert hashed != "s3cret-password"
    assert verify_password("s3cret-password", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_roundtrip() -> None:
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id)
    payload = decode_token(token, TOKEN_TYPE_ACCESS)
    assert payload["sub"] == user_id


def test_refresh_token_type_enforced() -> None:
    import jwt

    token = create_refresh_token(str(uuid.uuid4()))
    decode_token(token, TOKEN_TYPE_REFRESH)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, TOKEN_TYPE_ACCESS)
