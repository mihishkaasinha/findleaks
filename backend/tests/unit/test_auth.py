import pytest

from findleaks.auth import hash_password, verify_password, validate_token, create_token


def test_hash_password_not_plaintext():
    plain = "mysecretpassword"
    hashed = hash_password(plain)
    assert hashed != plain


def test_hash_password_produces_bcrypt_format():
    hashed = hash_password("testpass")
    assert hashed.startswith("$2b$")


def test_verify_password_correct():
    plain = "correctpassword"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("correctpassword")
    assert verify_password("wrongpassword", hashed) is False


def test_verify_password_empty_string():
    hashed = hash_password("password")
    assert verify_password("", hashed) is False


def test_verify_password_invalid_hash():
    assert verify_password("password", "not-a-bcrypt-hash") is False


def test_create_token_returns_string():
    token = create_token()
    assert isinstance(token, str)
    assert len(token) > 20


def test_create_token_unique():
    t1 = create_token()
    t2 = create_token()
    assert t1 != t2


def test_validate_token_returns_true_for_valid(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "my-test-secret-key")
    from findleaks.config import Settings, get_settings
    get_settings.cache_clear()
    assert validate_token("my-test-secret-key") is True
    get_settings.cache_clear()


def test_validate_token_returns_false_for_invalid(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "my-test-secret-key")
    from findleaks.config import get_settings
    get_settings.cache_clear()
    assert validate_token("wrong-token") is False
    get_settings.cache_clear()


def test_validate_token_returns_false_for_empty():
    assert validate_token("") is False
