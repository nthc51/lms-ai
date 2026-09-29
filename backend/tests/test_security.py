import uuid

import pytest

from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)


def test_hash_and_verify_password():
    h = hash_password("password123")
    assert h != "password123"
    assert verify_password("password123", h)
    assert not verify_password("wrong-pass", h)


def test_access_token_roundtrip():
    uid = uuid.uuid4()
    payload = decode_access_token(create_access_token(uid, "teacher"))
    assert payload["sub"] == str(uid)
    assert payload["role"] == "teacher"


def test_expired_access_token_raises_token_expired():
    token = create_access_token(uuid.uuid4(), "student", expires_minutes=-1)
    with pytest.raises(AppError) as e:
        decode_access_token(token)
    assert e.value.code == "TOKEN_EXPIRED" and e.value.status == 401


def test_garbage_token_raises_invalid_token():
    with pytest.raises(AppError) as e:
        decode_access_token("not-a-jwt")
    assert e.value.code == "INVALID_TOKEN"


def test_refresh_token_is_random_and_hashable():
    raw1, h1 = new_refresh_token()
    raw2, _ = new_refresh_token()
    assert raw1 != raw2 and len(raw1) >= 40
    assert hash_refresh_token(raw1) == h1 and len(h1) == 64
