"""Connexion PostgreSQL locale ou hébergée, sans journaliser les identifiants."""
from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


def database_settings(environment):
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": environment.get("DB_NAME", "azula"),
        "USER": environment.get("DB_USER", "azula"),
        "PASSWORD": environment.get("DB_PASSWORD", ""),
        "HOST": environment.get("DB_HOST", "127.0.0.1"),
        "PORT": environment.get("DB_PORT", "5432"),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"connect_timeout": 5},
        "TEST": {"NAME": environment.get("TEST_DB_NAME", "test_azula")},
    }
    try:
        config["CONN_MAX_AGE"] = int(environment.get("DB_CONN_MAX_AGE", "60"))
        if config["CONN_MAX_AGE"] < 0:
            raise ValueError
    except ValueError:
        raise ImproperlyConfigured("DB_CONN_MAX_AGE doit être un entier positif ou nul.") from None

    query = {}
    if environment.get("DATABASE_URL"):
        try:
            url = urlsplit(environment["DATABASE_URL"])
            if url.scheme not in {"postgres", "postgresql"} or not url.hostname or not url.path.strip("/"):
                raise ValueError
            if not url.username or url.fragment:
                raise ValueError
            config.update({
                "NAME": unquote(url.path[1:]),
                "USER": unquote(url.username),
                "PASSWORD": unquote(url.password or ""),
                "HOST": url.hostname,
                "PORT": str(url.port or 5432),
            })
            query = parse_qs(url.query, strict_parsing=True)
            if set(query) - {"sslmode", "sslrootcert", "channel_binding"} or any(len(values) != 1 for values in query.values()):
                raise ValueError
        except ValueError:
            raise ImproperlyConfigured(
                "DATABASE_URL PostgreSQL invalide ; paramètres admis : sslmode, sslrootcert, channel_binding."
            ) from None

    for option, variable in [("sslmode", "DB_SSLMODE"), ("sslrootcert", "DB_SSLROOTCERT"), ("channel_binding", "DB_CHANNEL_BINDING")]:
        value = environment.get(variable) or query.get(option, [None])[0]
        if value:
            config["OPTIONS"][option] = value
    if config["OPTIONS"].get("sslmode") not in {None, "disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
        raise ImproperlyConfigured("DB_SSLMODE n’est pas un mode TLS PostgreSQL reconnu.")
    if config["OPTIONS"].get("channel_binding") not in {None, "disable", "prefer", "require"}:
        raise ImproperlyConfigured("DB_CHANNEL_BINDING n’est pas une valeur PostgreSQL reconnue.")

    if environment.get("DB_TRANSACTION_POOLING", "0") == "1":
        config["DISABLE_SERVER_SIDE_CURSORS"] = True
        config["OPTIONS"]["prepare_threshold"] = None
    return config
