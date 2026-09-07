"""Disponibilité PostgreSQL et confiance explicite dans le proxy d'hébergement."""

from unittest.mock import patch

import pytest
from django.core.handlers.wsgi import WSGIRequest
from django.db import OperationalError
from django.test import Client, RequestFactory, override_settings
from waitress.proxy_headers import proxy_headers_middleware

from server import server_options


@pytest.mark.django_db
def test_health_checks_postgresql_without_a_session():
    response = Client().get("/healthz/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "no-store" in response["Cache-Control"]
    assert not response.cookies


def test_health_returns_unavailable_without_exposing_connection_errors():
    with patch("config.views.connection.cursor", side_effect=OperationalError("private database credentials")):
        response = Client().get("/healthz/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "private database credentials" not in response.content.decode()
    assert "no-store" in response["Cache-Control"]


def test_health_does_not_accept_writes():
    response = Client().post("/healthz/")
    assert response.status_code == 405


@override_settings(SECURE_SSL_REDIRECT=True)
def test_only_exact_health_path_is_exempt_from_https_redirect():
    with patch("config.views.connection.cursor", side_effect=OperationalError):
        assert Client().get("/healthz/").status_code == 503
    assert Client().get("/login").status_code == 301
    assert Client().get("/healthz/extra").status_code == 301


def test_local_server_strips_forwarded_headers_even_if_proxy_variable_is_set():
    options = server_options({"TRUSTED_PROXY": "*"})
    assert options["listen"] == "0.0.0.0:8000"
    assert options["clear_untrusted_proxy_headers"] is True
    assert "trusted_proxy" not in options


def test_proxy_configuration_preserves_https_and_client_address_only():
    options = server_options({"PORT": "9000", "TRUST_HTTPS_PROXY": "1", "TRUSTED_PROXY": "10.0.0.5"})
    assert options["listen"] == "0.0.0.0:9000"
    assert options["trusted_proxy"] == "10.0.0.5"
    assert options["trusted_proxy_count"] == 1
    assert options["trusted_proxy_headers"] == {"x-forwarded-proto", "x-forwarded-for"}
    assert options["clear_untrusted_proxy_headers"] is True


@pytest.mark.parametrize("peer,secure,address", [("10.0.0.5", True, "192.0.2.20"), ("192.0.2.99", False, "192.0.2.99")])
@override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
def test_waitress_passes_only_trusted_https_and_client_address_to_django(peer, secure, address):
    options = server_options({"TRUST_HTTPS_PROXY": "1", "TRUSTED_PROXY": "10.0.0.5"})
    captured = []

    def application(environ, start_response):
        captured.append(WSGIRequest(environ))
        start_response("200 OK", [])
        return []

    middleware = proxy_headers_middleware(
        application,
        trusted_proxy=options["trusted_proxy"],
        trusted_proxy_count=options["trusted_proxy_count"],
        trusted_proxy_headers=options["trusted_proxy_headers"],
        clear_untrusted=options["clear_untrusted_proxy_headers"],
    )
    environ = RequestFactory().get(
        "/login", REMOTE_ADDR=peer, HTTP_HOST="erp.example.invalid",
        HTTP_X_FORWARDED_PROTO="https", HTTP_X_FORWARDED_FOR="198.51.100.1, 192.0.2.20",
        HTTP_X_FORWARDED_HOST="attacker.example.invalid",
    ).environ
    middleware(environ, lambda status, headers: None)
    request = captured[0]
    assert request.is_secure() is secure
    assert request.META["REMOTE_ADDR"] == address
    assert request.META["HTTP_HOST"] == "erp.example.invalid"
    assert "HTTP_X_FORWARDED_HOST" not in request.META


@pytest.mark.parametrize("proxy", ["", "   ", "proxy.example.invalid"])
def test_proxy_trust_requires_an_explicit_valid_peer(proxy):
    with pytest.raises(ValueError, match="TRUSTED_PROXY"):
        server_options({"TRUST_HTTPS_PROXY": "1", "TRUSTED_PROXY": proxy})


def test_wildcard_proxy_is_an_explicit_deployment_choice():
    assert server_options({"TRUST_HTTPS_PROXY": "1", "TRUSTED_PROXY": "*"})["trusted_proxy"] == "*"


@pytest.mark.parametrize("port", ["secret-value", "0", "65536"])
def test_invalid_port_is_refused_without_echoing_its_value(port):
    with pytest.raises(ValueError, match="PORT doit être un entier") as error:
        server_options({"PORT": port})
    if port == "secret-value":
        assert port not in str(error.value)
