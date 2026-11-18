from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
import pytest

from app.core import security
from app.core.config import settings

KEY = settings.SECRET_KEY.get_secret_value()


def _encode(payload: dict[str, object], key: str = KEY, algorithm: str = "HS256") -> str:
    return jwt.encode(payload, key, algorithm=algorithm)


def _in(minutes: int) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


class TestPasswords:
    def test_new_hashes_use_argon2(self) -> None:
        assert security.hash_password("Sm0ke-pass").startswith("$argon2id$")

    def test_verify_correct_and_wrong(self) -> None:
        hashed = security.hash_password("Sm0ke-pass")
        assert security.verify_password("Sm0ke-pass", hashed)
        assert not security.verify_password("wrong", hashed)

    def test_legacy_bcrypt_hash_still_verifies(self) -> None:
        legacy = bcrypt.hashpw(b"legacy-pass", bcrypt.gensalt(rounds=4)).decode()
        assert security.verify_password("legacy-pass", legacy)
        assert not security.verify_password("other", legacy)

    @pytest.mark.parametrize("stored", ["", "not-a-hash", "$2b$broken"])
    def test_corrupt_stored_hash_means_wrong_password(self, stored: str) -> None:
        assert security.verify_password("anything", stored) is False

    def test_password_longer_than_bcrypt_limit(self) -> None:
        long_password = "П" * 60  # 120 bytes in UTF-8
        assert security.verify_password(long_password, security.hash_password(long_password))


class TestTokens:
    def test_access_token_roundtrip(self) -> None:
        token = security.create_access_token({"sub": "42"})
        payload = security.decode_token(token, expected_type="access")
        assert payload["sub"] == "42"
        assert payload["type"] == "access"

    def test_token_types_are_not_interchangeable(self) -> None:
        access = security.create_access_token({"sub": "1"})
        refresh = security.create_refresh_token({"sub": "1"})
        with pytest.raises(security.TokenError):
            security.decode_token(refresh, expected_type="access")
        with pytest.raises(security.TokenError):
            security.decode_token(access, expected_type="refresh")

    @pytest.mark.parametrize(
        "token_factory",
        [
            pytest.param(
                lambda: _encode({"sub": "1", "type": "access", "exp": _in(-1)}), id="expired"
            ),
            pytest.param(lambda: _encode({"sub": "1", "type": "access"}), id="no-exp"),
            pytest.param(
                lambda: _encode(
                    {"sub": "1", "type": "access", "exp": _in(5)}, key="another-key-" + "0" * 32
                ),
                id="wrong-key",
            ),
            pytest.param(
                lambda: jwt.encode(
                    {"sub": "1", "type": "access", "exp": _in(5)}, None, algorithm="none"
                ),
                id="alg-none",
            ),
            pytest.param(lambda: "abc.def.ghi", id="garbage"),
        ],
    )
    def test_invalid_tokens_are_rejected(self, token_factory) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(security.TokenError):
            security.decode_token(token_factory(), expected_type="access")

    def test_tampered_signature_is_rejected(self) -> None:
        token = security.create_access_token({"sub": "1"})
        header, payload, signature = token.split(".")
        tampered = ".".join([header, payload, signature[::-1]])
        with pytest.raises(security.TokenError):
            security.decode_token(tampered, expected_type="access")
