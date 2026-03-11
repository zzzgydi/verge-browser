from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_development_defaults_allow_local_bootstrap() -> None:
    settings = Settings()
    assert settings.admin_auth_token == "dev-admin-token"
    assert settings.ticket_secret == "ticket-secret"


def test_admin_token_must_be_present() -> None:
    with pytest.raises(ValidationError, match="VERGE_ADMIN_AUTH_TOKEN"):
        Settings(admin_auth_token="")


def test_non_development_requires_non_default_admin_token() -> None:
    with pytest.raises(ValidationError, match="VERGE_ADMIN_AUTH_TOKEN"):
        Settings(env="production", admin_auth_token="dev-admin-token", ticket_secret="x" * 32)


def test_non_development_requires_strong_ticket_secret() -> None:
    with pytest.raises(ValidationError, match="VERGE_TICKET_SECRET"):
        Settings(env="production", admin_auth_token="x" * 16, ticket_secret="ticket-secret")


def test_non_development_accepts_strong_secrets() -> None:
    settings = Settings(env="production", admin_auth_token="x" * 16, ticket_secret="y" * 32)
    assert settings.env == "production"
