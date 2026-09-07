"""Vérifier les URL hébergées, le TLS et l'absence de secret dans les erreurs."""
import pytest
from django.core.exceptions import ImproperlyConfigured

from config.database import database_settings


def test_hosted_url_decodes_credentials_and_enforces_requested_tls():
    config = database_settings({
        "DATABASE_URL": "postgresql://app%40azula:p%40ss%3Aword@db.example.invalid:6543/azula?sslmode=verify-full&channel_binding=require",
        "DB_SSLROOTCERT": "/run/secrets/postgres-ca.pem",
        "DB_CONN_MAX_AGE": "0",
    })
    assert config["USER"] == "app@azula"
    assert config["PASSWORD"] == "p@ss:word"
    assert config["PORT"] == "6543"
    assert config["NAME"] == "azula"
    assert config["CONN_MAX_AGE"] == 0
    assert config["OPTIONS"]["sslmode"] == "verify-full"
    assert config["OPTIONS"]["sslrootcert"] == "/run/secrets/postgres-ca.pem"
    assert config["OPTIONS"]["channel_binding"] == "require"


@pytest.mark.parametrize("url", [
    "sqlite:///local.db", "https://app:secret@db.invalid/data",
    "postgres://app:secret@db.invalid:wrong/data", "postgres://app:secret@db.invalid/",
    "postgres://app:secret@db.invalid/data?options=unsafe",
    "postgres://app:secret@db.invalid/data?sslmode=require&sslmode=disable",
])
def test_invalid_url_error_never_contains_credentials(url):
    with pytest.raises(ImproperlyConfigured) as error:
        database_settings({"DATABASE_URL": url})
    assert "secret" not in str(error.value)
    assert url not in str(error.value)


def test_transaction_pooler_does_not_reuse_server_side_cursor_or_prepared_statement():
    config = database_settings({"DB_TRANSACTION_POOLING": "1", "DB_HOST": "pooler.example.invalid"})
    assert config["DISABLE_SERVER_SIDE_CURSORS"] is True
    assert config["OPTIONS"]["prepare_threshold"] is None


def test_explicit_tls_environment_takes_precedence_over_provider_url():
    config = database_settings({
        "DATABASE_URL": "postgres://app:example@db.invalid/azula?sslmode=require",
        "DB_SSLMODE": "verify-full",
    })
    assert config["OPTIONS"]["sslmode"] == "verify-full"


@pytest.mark.parametrize("environment", [{"DB_SSLMODE": "typo"}, {"DB_CONN_MAX_AGE": "-1"}])
def test_invalid_connection_configuration_fails_before_connecting(environment):
    with pytest.raises(ImproperlyConfigured):
        database_settings(environment)
