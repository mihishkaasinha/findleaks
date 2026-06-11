import pytest
from pydantic import ValidationError


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "testsecret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "tw_token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg_token")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "pass")

    from findleaks.config import Settings
    settings = Settings()
    assert settings.SECRET_KEY == "testsecret"
    assert settings.APP_NAME == "FINDLEAKS"
    assert settings.ALERT_THRESHOLD_HIGH == 0.80
    assert settings.TOKEN_EXPIRY_BUFFER == 100


def test_settings_fails_without_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "tw_token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg_token")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "pass")

    from findleaks.config import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "secret_key" in str(exc_info.value).lower()


def test_settings_fails_with_invalid_database_url(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "testsecret")
    monkeypatch.setenv("DATABASE_URL", "mysql://wrong_db")
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "tw_token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg_token")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "pass")

    from findleaks.config import Settings
    with pytest.raises(ValidationError):
        Settings()


def test_settings_fails_with_threshold_out_of_range(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "testsecret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "tw_token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg_token")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "pass")
    monkeypatch.setenv("ALERT_THRESHOLD_HIGH", "1.5")

    from findleaks.config import Settings
    with pytest.raises(ValidationError):
        Settings()


def test_settings_sqlite_url_accepted(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "testsecret")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "tw_token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg_token")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "pass")

    from findleaks.config import Settings
    settings = Settings()
    assert "sqlite" in settings.DATABASE_URL
