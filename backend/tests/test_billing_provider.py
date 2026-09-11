"""Contrat Stripe synthétique : aucun réseau, paiement ni accès à une base."""

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import Mock
from urllib.parse import parse_qs

import pytest

from billing import provider

NOW = 1_789_200_000
WEBHOOK_SECRET = "whsec_syntheticWebhookSecret123456"


@pytest.fixture(autouse=True)
def stripe_settings(settings, monkeypatch):
    settings.STRIPE_SECRET_KEY = "sk_test_fake0000"
    settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET
    settings.STRIPE_API_VERSION = provider.SUPPORTED_API_VERSION
    settings.STRIPE_LIVE_MODE = False
    monkeypatch.setattr(provider.time, "time", lambda: NOW)
    # Tout appel réseau doit être remplacé explicitement par une réponse synthétique.
    monkeypatch.setattr(provider, "HTTPSConnection", Mock(side_effect=AssertionError("network_forbidden")))


def transport(monkeypatch, payload, status=200):
    response = Mock(status=status)
    response.read.return_value = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    connection = Mock()
    connection.getresponse.return_value = response
    constructor = Mock(return_value=connection)
    monkeypatch.setattr(provider, "HTTPSConnection", constructor)
    return constructor, connection, response


def event(**updates):
    value = {"id": "evt_synthetic1", "object": "event", "type": "customer.subscription.updated",
             "created": NOW, "api_version": provider.SUPPORTED_API_VERSION, "livemode": False,
             "data": {"object": {"id": "sub_synthetic1", "object": "subscription"}}}
    value.update(updates)
    return json.dumps(value).encode()


def signature(body, timestamp=NOW):
    digest = hmac.new(WEBHOOK_SECRET.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def checkout_args():
    return {"customer_id": "cus_synthetic1", "price_id": "price_synthetic1", "company_id": 7,
            "success_url": "https://erp.example/billing?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": "https://erp.example/billing", "idempotency_key": "checkout-7-request-1"}


def test_customer_request_has_fixed_tls_host_version_and_idempotency(monkeypatch):
    constructor, connection, response = transport(monkeypatch, {
        "id": "cus_synthetic1", "object": "customer", "livemode": False,
    })
    result = provider.create_customer(7, "Société synthétique", "billing@example.test", "customer-7")
    constructor.assert_called_once_with("api.stripe.com", timeout=10)
    method, path = connection.request.call_args.args
    options = connection.request.call_args.kwargs
    assert (method, path) == ("POST", "/v1/customers")
    assert options["headers"]["Stripe-Version"] == "2026-08-26.dahlia"
    assert options["headers"]["Idempotency-Key"] == "customer-7"
    assert options["headers"]["Authorization"].startswith("Bearer sk_test_")
    assert parse_qs(options["body"].decode())["metadata[azula_company_id]"] == ["7"]
    response.read.assert_called_once_with(provider.MAX_BODY_BYTES + 1)
    connection.close.assert_called_once()
    assert result["id"] == "cus_synthetic1"


def test_checkout_uses_one_configured_price_and_stable_trial_expiry(monkeypatch):
    _, connection, _ = transport(monkeypatch, {
        "id": "cs_test_synthetic1", "object": "checkout.session", "livemode": False,
        "url": "https://checkout.stripe.com/c/pay/cs_test_synthetic1#fragment",
    })
    for _ in range(2):
        provider.create_checkout(**checkout_args(), trial_days=14, expires_at=NOW + 3600, checkout_reference="81")
    first, second = connection.request.call_args_list
    assert first == second
    data = parse_qs(first.kwargs["body"].decode())
    assert data["mode"] == ["subscription"]
    assert data["line_items[0][price]"] == ["price_synthetic1"]
    assert data["line_items[0][quantity]"] == ["1"]
    assert data["subscription_data[metadata][azula_company_id]"] == ["7"]
    assert data["metadata[azula_company_id]"] == data["client_reference_id"] == ["7"]
    assert data["subscription_data[trial_period_days]"] == ["14"]
    assert data["expires_at"] == [str(NOW + 3600)]
    assert data["metadata[azula_checkout_attempt]"] == ["81"]
    assert data["payment_method_collection"] == ["always"]
    assert data["adaptive_pricing[enabled]"] == ["false"]
    assert not any("unit_amount" in key for key in data)


def test_portal_has_idempotency_header_and_only_stripe_host(monkeypatch):
    _, connection, _ = transport(monkeypatch, {
        "id": "bps_synthetic1", "object": "billing_portal.session", "livemode": False,
        "url": "https://billing.stripe.com/p/session?secret=synthetic",
    })
    provider.create_portal("cus_synthetic1", "https://erp.example/billing")
    assert connection.request.call_args.args == ("POST", "/v1/billing_portal/sessions")
    assert connection.request.call_args.kwargs["headers"]["Idempotency-Key"].startswith("azula-portal-")


@pytest.mark.parametrize("method,identifier,object_type,path", [
    (provider.retrieve_subscription, "sub_synthetic1", "subscription", "/v1/subscriptions/sub_synthetic1?expand%5B%5D=latest_invoice"),
    (provider.retrieve_price, "price_synthetic1", "price", "/v1/prices/price_synthetic1"),
    (provider.retrieve_checkout, "cs_test_synthetic1", "checkout.session", "/v1/checkout/sessions/cs_test_synthetic1"),
])
def test_retrieve_verifies_resource_identity(monkeypatch, method, identifier, object_type, path):
    _, connection, _ = transport(monkeypatch, {"id": identifier, "object": object_type, "livemode": False})
    assert method(identifier)["id"] == identifier
    assert connection.request.call_args.args == ("GET", path)
    assert "Idempotency-Key" not in connection.request.call_args.kwargs["headers"]
    transport(monkeypatch, {"id": identifier + "other", "object": object_type, "livemode": False})
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        method(identifier)


def test_expire_checkout_has_stable_idempotency_key(monkeypatch):
    _, connection, _ = transport(monkeypatch, {
        "id": "cs_test_synthetic1", "object": "checkout.session", "livemode": False, "status": "expired",
    })
    assert provider.expire_checkout("cs_test_synthetic1")["status"] == "expired"
    assert connection.request.call_args.args == ("POST", "/v1/checkout/sessions/cs_test_synthetic1/expire")
    assert connection.request.call_args.kwargs["headers"]["Idempotency-Key"] == "azula-expire-cs_test_synthetic1"


@pytest.mark.parametrize("url", [
    "http://checkout.stripe.com/pay", "https://checkout.stripe.com.evil.example/pay",
    "https://checkout.stripe.com@evil.example/pay", "https://evil@checkout.stripe.com/pay",
    "https://checkout.stripe.com:444/pay", "javascript:alert(1)", "//checkout.stripe.com/pay",
    "https://checkout.stripe.com\\@evil.example/pay", "https://checkout.stripe.com/pay\n",
    "https://billing.stripe.com/pay", "https://checkout.stripe.com",
])
def test_checkout_rejects_unsafe_provider_redirect(monkeypatch, url):
    transport(monkeypatch, {"id": "cs_test_synthetic1", "object": "checkout.session", "livemode": False, "url": url})
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        provider.create_checkout(**checkout_args())


@pytest.mark.parametrize("changes", [
    {"customer_id": "cus_x/../../customers"}, {"price_id": "price_x?expand=data"},
    {"company_id": True}, {"company_id": "0"}, {"company_id": "7\n"},
    {"success_url": "https://user:secret@erp.example/"}, {"cancel_url": "http://erp.example/"},
    {"idempotency_key": "key\r\nInjected: secret"}, {"trial_days": True}, {"trial_days": 731},
    {"trial_days": 1}, {"expires_at": 1.5}, {"expires_at": True},
])
def test_invalid_checkout_inputs_never_open_network(changes):
    arguments = checkout_args() | changes
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        provider.create_checkout(**arguments)
    provider.HTTPSConnection.assert_not_called()


@pytest.mark.parametrize("overrides", [
    {"STRIPE_SECRET_KEY": ""}, {"STRIPE_SECRET_KEY": "sk_live_fake0000"},
    {"STRIPE_LIVE_MODE": "false"}, {"STRIPE_API_VERSION": "2026-02-25.clover"},
])
def test_inconsistent_configuration_never_opens_network(settings, overrides):
    for key, value in overrides.items():
        setattr(settings, key, value)
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        provider.retrieve_price("price_synthetic1")
    provider.HTTPSConnection.assert_not_called()


@pytest.mark.parametrize("status", [301, 302, 307, 400, 401, 429, 500])
def test_http_failures_are_sanitized_without_reading_error_body(monkeypatch, status):
    _, connection, response = transport(monkeypatch, b'{"error":"secret body"}', status)
    with pytest.raises(provider.ProviderError) as error:
        provider.retrieve_price("price_synthetic1")
    assert str(error.value) == error.value.code == "billing_unavailable"
    response.read.assert_not_called()
    connection.request.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("body", [
    b"[]", b"null", b"not-json", b"\xff", b'{"livemode":false,"livemode":true}',
    b'{"livemode":false,"bad":NaN}', b'{"livemode":false,"bad":Infinity}',
    b" " * (provider.MAX_BODY_BYTES + 1),
], ids=["array", "null", "syntax", "utf8", "duplicate", "nan", "infinity", "oversize"])
def test_invalid_json_and_large_responses_are_sanitized(monkeypatch, body):
    transport(monkeypatch, body)
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        provider.retrieve_price("price_synthetic1")


@pytest.mark.parametrize("mode", [True, None, "false", 0])
def test_response_mode_must_be_exact_boolean(monkeypatch, mode):
    transport(monkeypatch, {"id": "price_synthetic1", "object": "price", "livemode": mode})
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        provider.retrieve_price("price_synthetic1")


def test_socket_failure_has_no_provider_exception_text(monkeypatch):
    constructor = Mock(side_effect=TimeoutError("must-not-expose-private-uri"))
    monkeypatch.setattr(provider, "HTTPSConnection", constructor)
    with pytest.raises(provider.ProviderError) as error:
        provider.retrieve_price("price_synthetic1")
    assert str(error.value) == "billing_unavailable"
    assert error.value.__suppress_context__ is True


def test_json_decimals_are_exact_not_floats(monkeypatch):
    transport(monkeypatch, b'{"id":"price_synthetic1","object":"price","livemode":false,"exact":0.100000000000000001}')
    result = provider.retrieve_price("price_synthetic1")
    assert result["exact"] == Decimal("0.100000000000000001")
    assert isinstance(result["exact"], Decimal)


def test_webhook_authenticates_raw_bytes_and_accepts_rotation_signatures():
    body = event()
    assert provider.verify_event(body, signature(body))["id"] == "evt_synthetic1"
    assert provider.verify_event(body, f"v1={'0' * 64}," + signature(body))["id"] == "evt_synthetic1"
    assert provider.verify_event(body, signature(body) + ",v0=ignored")["livemode"] is False
    with pytest.raises(provider.ProviderError, match="^billing_invalid_event$"):
        provider.verify_event(body + b" ", signature(body))


@pytest.mark.parametrize("offset", [-301, 301])
def test_webhook_rejects_expired_and_future_signatures(offset):
    body = event()
    with pytest.raises(provider.ProviderError, match="^billing_invalid_event$"):
        provider.verify_event(body, signature(body, NOW + offset))


@pytest.mark.parametrize("offset", [-300, 300])
def test_webhook_accepts_tolerance_boundaries(offset):
    body = event()
    assert provider.verify_event(body, signature(body, NOW + offset))["id"] == "evt_synthetic1"


@pytest.mark.parametrize("header", [None, "", "malformed", "t=1,v1=bad", "x=" + "x" * 8192,
    f"t={NOW},t={NOW},v1=" + "a" * 64, f"t={NOW},v0=" + "a" * 64])
def test_webhook_rejects_malformed_signature(header):
    with pytest.raises(provider.ProviderError, match="^billing_invalid_event$"):
        provider.verify_event(event(), header)


@pytest.mark.parametrize("changes", [
    {"livemode": True}, {"livemode": 0}, {"api_version": "2025-03-31.basil"},
    {"id": "evt_bad/uri"}, {"object": "v2.core.event"}, {"created": True}, {"created": -1},
    {"data": {}}, {"data": {"object": []}}, {"type": "bad\n"},
])
def test_webhook_rejects_unexpected_contract(changes):
    body = event(**changes)
    with pytest.raises(provider.ProviderError, match="^billing_invalid_event$"):
        provider.verify_event(body, signature(body))


@pytest.mark.parametrize("body", [b"[]", b"\xff", b"{", b'{"id":1,"id":2}',
    b'{"value":NaN}', b" " * (provider.MAX_BODY_BYTES + 1)],
    ids=["array", "utf8", "syntax", "duplicate", "nan", "oversize"])
def test_webhook_rejects_signed_invalid_or_oversized_json(body):
    with pytest.raises(provider.ProviderError, match="^billing_invalid_event$"):
        provider.verify_event(body, signature(body))


def test_webhook_rejects_unconfigured_secret(settings):
    settings.STRIPE_WEBHOOK_SECRET = ""
    body = event()
    with pytest.raises(provider.ProviderError, match="^billing_invalid_event$"):
        provider.verify_event(body, signature(body))


def test_live_mode_requires_explicit_matching_keys_and_events(settings, monkeypatch):
    settings.STRIPE_LIVE_MODE = True
    settings.STRIPE_SECRET_KEY = "sk_live_fake0000"
    transport(monkeypatch, {"id": "price_synthetic1", "object": "price", "livemode": True})
    assert provider.retrieve_price("price_synthetic1")["livemode"] is True
    body = event(livemode=True)
    assert provider.verify_event(body, signature(body))["livemode"] is True
    arguments = checkout_args() | {"success_url": "http://localhost:8081/billing"}
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        provider.create_checkout(**arguments)


def listed_checkout(**changes):
    return {"id": "cs_test_synthetic1", "object": "checkout.session", "livemode": False,
            "customer": "cus_synthetic1", "mode": "subscription", "status": "open",
            "metadata": {"azula_checkout_attempt": "81"},
            "url": "https://checkout.stripe.com/c/pay/cs_test_synthetic1"} | changes


def test_find_checkout_matches_stable_attempt_reference_and_customer(monkeypatch):
    candidate = listed_checkout()
    _, connection, _ = transport(monkeypatch, {"object": "list", "data": [
        listed_checkout(id="cs_test_unrelated", metadata={}), candidate,
    ], "has_more": False})
    assert provider.find_checkout("cus_synthetic1", "81") == candidate
    assert connection.request.call_args.args == ("GET", "/v1/checkout/sessions?customer=cus_synthetic1&limit=100")
    assert "Idempotency-Key" not in connection.request.call_args.kwargs["headers"]


def test_find_checkout_returns_none_only_after_complete_unmatched_page(monkeypatch):
    transport(monkeypatch, {"object": "list", "data": [listed_checkout(metadata={})], "has_more": False})
    assert provider.find_checkout("cus_synthetic1", "81") is None
    transport(monkeypatch, {"object": "list", "data": [], "has_more": False})
    assert provider.find_checkout("cus_synthetic1", "81") is None


def test_find_checkout_refuses_incomplete_negative_result(monkeypatch):
    transport(monkeypatch, {"object": "list", "data": [listed_checkout(metadata={})], "has_more": True})
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        provider.find_checkout("cus_synthetic1", "81")


def test_find_checkout_accepts_found_session_even_when_unrelated_older_pages_exist(monkeypatch):
    candidate = listed_checkout(status="complete", url=None)
    transport(monkeypatch, {"object": "list", "data": [candidate], "has_more": True})
    assert provider.find_checkout("cus_synthetic1", "81") == candidate


def test_find_checkout_refuses_duplicate_attempt_reference(monkeypatch):
    transport(monkeypatch, {"object": "list", "data": [
        listed_checkout(), listed_checkout(id="cs_test_synthetic2"),
    ], "has_more": False})
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        provider.find_checkout("cus_synthetic1", "81")


@pytest.mark.parametrize("changes", [
    {"customer": "cus_other"}, {"livemode": True}, {"object": "customer"}, {"id": "cs_unsafe/uri"},
    {"mode": "payment"}, {"metadata": []}, {"url": "https://evil.example/session"},
])
def test_find_checkout_rejects_inconsistent_candidate(monkeypatch, changes):
    transport(monkeypatch, {"object": "list", "data": [listed_checkout(**changes)], "has_more": False})
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        provider.find_checkout("cus_synthetic1", "81")


@pytest.mark.parametrize("payload", [
    {"object": "list", "data": [], "has_more": 0}, {"object": "list", "data": {} , "has_more": False},
    {"object": "customer", "data": [], "has_more": False},
    {"object": "list", "data": [None], "has_more": False},
    {"object": "list", "data": [listed_checkout()] * 101, "has_more": False},
], ids=["nonboolean-page", "wrong-data-type", "wrong-list-type", "wrong-candidate-type", "too-many"])
def test_find_checkout_rejects_invalid_list_contract(monkeypatch, payload):
    transport(monkeypatch, payload)
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        provider.find_checkout("cus_synthetic1", "81")


@pytest.mark.parametrize("reference", [None, "", "0", True, "81\n"])
def test_find_checkout_invalid_reference_never_opens_network(reference):
    with pytest.raises(provider.ProviderError, match="^billing_unavailable$"):
        provider.find_checkout("cus_synthetic1", reference)
    provider.HTTPSConnection.assert_not_called()
