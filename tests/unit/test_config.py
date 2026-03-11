from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_development_defaults_allow_local_bootstrap() -> None:
    settings = Settings()
    assert settings.jwt_secret == "dev-secret"
    assert settings.ticket_secret == "ticket-secret"


def test_non_development_requires_strong_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="VERGE_JWT_SECRET"):
        Settings(env="production", jwt_secret="dev-secret", ticket_secret="x" * 32)


def test_non_development_requires_strong_ticket_secret() -> None:
    with pytest.raises(ValidationError, match="VERGE_TICKET_SECRET"):
        Settings(env="production", jwt_secret="x" * 32, ticket_secret="ticket-secret")


def test_non_development_accepts_strong_secrets() -> None:
    settings = Settings(env="production", jwt_secret="x" * 32, ticket_secret="y" * 32)
    assert settings.env == "production"
