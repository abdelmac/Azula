"""Transport Stripe borné ; aucune donnée bancaire ni réponse brute dans les erreurs."""

import hashlib
import hmac
import json
import re
import time
from decimal import Decimal, DecimalException
from http.client import HTTPException, HTTPSConnection
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from django.conf import settings

SUPPORTED_API_VERSION = "2026-08-26.dahlia"
MAX_BODY_BYTES = 1_048_576
REQUEST_TIMEOUT_SECONDS = 10
SIGNATURE_TOLERANCE_SECONDS = 300


class ProviderError(Exception):
    """Code public stable, sans texte, URL, identifiant ou secret du prestataire."""

    def __init__(self, code="billing_unavailable"):
        self.code = code if code in {"billing_unavailable", "billing_invalid_event"} else "billing_unavailable"
        super().__init__(self.code)


def _mode():
    mode = getattr(settings, "STRIPE_LIVE_MODE", False)
    if type(mode) is not bool:
        raise ProviderError()
    return mode


def _version():
    version = getattr(settings, "STRIPE_API_VERSION", SUPPORTED_API_VERSION)
    if version != SUPPORTED_API_VERSION:
        raise ProviderError()
    return version


def _identifier(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9_]{1,240}", value):
        raise ProviderError()
    return value


def _company_id(value):
    if type(value) not in {str, int} or not re.fullmatch(r"[1-9][0-9]{0,18}", str(value)):
        raise ProviderError()
    return str(value)


def _text(value, limit, *, optional=False):
    if not isinstance(value, str) or len(value) > limit or (not value and not optional):
        raise ProviderError()
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ProviderError()
    return value


def _return_url(value):
    _text(value, 2048)
    try:
        parsed = urlsplit(value)
        allowed_local = not _mode() and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (parsed.scheme != "https" and not (parsed.scheme == "http" and allowed_local)) or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None or "\\" in value:
            raise ValueError
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
    except ValueError:
        raise ProviderError() from None
    return value


def _hosted_url(value, host):
    _text(value, 8192)
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.hostname != host or parsed.port not in {None, 443}
                or parsed.username is not None or parsed.password is not None or "\\" in value
                or not parsed.path.startswith("/")):
            raise ValueError
    except ValueError:
        raise ProviderError() from None
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError


def _json_object(raw_body, code="billing_unavailable"):
    if not isinstance(raw_body, bytes) or not raw_body or len(raw_body) > MAX_BODY_BYTES:
        raise ProviderError(code)
    try:
        value = json.loads(raw_body.decode("utf-8"), parse_float=Decimal,
                           parse_constant=_invalid_constant, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError, RecursionError, DecimalException, OverflowError):
        raise ProviderError(code) from None
    if not isinstance(value, dict):
        raise ProviderError(code)
    return value


def _request(method, path, data=None, *, idempotency_key=None, collection=False):
    """Hôte fixe, TLS Python vérifié par défaut, aucun proxy ni suivi de redirection."""
    key = getattr(settings, "STRIPE_SECRET_KEY", "")
    mode_name = "live" if _mode() else "test"
    if not isinstance(key, str) or not re.fullmatch(r"(?:sk|rk)_" + mode_name + r"_[A-Za-z0-9]{8,256}", key):
        raise ProviderError()
    if method not in {"GET", "POST"} or not re.fullmatch(r"/v1/[a-zA-Z0-9_/]+", path):
        raise ProviderError()
    headers = {"Authorization": f"Bearer {key}", "Stripe-Version": _version(), "Accept": "application/json"}
    body = None
    if method == "POST":
        if not isinstance(idempotency_key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,255}", idempotency_key):
            raise ProviderError()
        headers["Idempotency-Key"] = idempotency_key
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = urlencode(data or {}).encode("utf-8")
    elif data:
        path += "?" + urlencode(data)
    connection = None
    try:
        connection = HTTPSConnection("api.stripe.com", timeout=REQUEST_TIMEOUT_SECONDS)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        # Refuser aussi les 3xx ; ne jamais transmettre Authorization à un autre hôte.
        if not 200 <= response.status < 300:
            raise ProviderError()
        result = _json_object(response.read(MAX_BODY_BYTES + 1))
        if collection:
            if (result.get("object") != "list" or not isinstance(result.get("data"), list)
                    or len(result["data"]) > 100 or type(result.get("has_more")) is not bool):
                raise ProviderError()
        elif result.get("livemode") is not _mode():
            raise ProviderError()
        return result
    except (HTTPException, OSError, ValueError):
        raise ProviderError() from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass


def _resource(result, object_type, prefix, expected_id=None):
    if result.get("object") != object_type:
        raise ProviderError()
    identifier = _identifier(result.get("id"), prefix)
    if expected_id is not None and identifier != expected_id:
        raise ProviderError()
    return result


def create_customer(company_id, name, email, idempotency_key):
    data = {"name": _text(name, 256), "metadata[azula_company_id]": _company_id(company_id)}
    if _text(email, 254, optional=True):
        data["email"] = email
    return _resource(_request("POST", "/v1/customers", data, idempotency_key=idempotency_key), "customer", "cus_")


def create_checkout(customer_id, price_id, company_id, success_url, cancel_url, idempotency_key,
                    trial_days=0, expires_at=None, checkout_reference=None):
    company = _company_id(company_id)
    data = {
        "customer": _identifier(customer_id, "cus_"),
        "mode": "subscription",
        "line_items[0][price]": _identifier(price_id, "price_"),
        "line_items[0][quantity]": "1",
        "client_reference_id": company,
        "metadata[azula_company_id]": company,
        "subscription_data[metadata][azula_company_id]": company,
        "success_url": _return_url(success_url),
        "cancel_url": _return_url(cancel_url),
        "payment_method_collection": "always",
        "adaptive_pricing[enabled]": "false",
        "locale": "auto",
    }
    if type(trial_days) is not int or not (trial_days == 0 or 2 <= trial_days <= 730):
        raise ProviderError()
    if trial_days:
        data["subscription_data[trial_period_days]"] = str(trial_days)
    if expires_at is not None:
        if type(expires_at) is not int or not 1 <= expires_at <= 253402300799:
            raise ProviderError()
        # Le service fournit et conserve l'échéance ; aucun recalcul à une reprise.
        data["expires_at"] = str(expires_at)
    if checkout_reference is not None:
        data["metadata[azula_checkout_attempt]"] = _company_id(checkout_reference)
    result = _resource(_request("POST", "/v1/checkout/sessions", data, idempotency_key=idempotency_key),
                       "checkout.session", "cs_")
    _hosted_url(result.get("url"), "checkout.stripe.com")
    return result


def create_portal(customer_id, return_url):
    result = _resource(_request("POST", "/v1/billing_portal/sessions", {
        "customer": _identifier(customer_id, "cus_"), "return_url": _return_url(return_url),
    }, idempotency_key=f"azula-portal-{uuid4().hex}"), "billing_portal.session", "bps_")
    _hosted_url(result.get("url"), "billing.stripe.com")
    return result


def retrieve_subscription(subscription_id):
    identifier = _identifier(subscription_id, "sub_")
    return _resource(_request("GET", f"/v1/subscriptions/{identifier}", {"expand[]": "latest_invoice"}),
                     "subscription", "sub_", identifier)


def retrieve_price(price_id):
    identifier = _identifier(price_id, "price_")
    return _resource(_request("GET", f"/v1/prices/{identifier}"), "price", "price_", identifier)


def retrieve_checkout(session_id):
    identifier = _identifier(session_id, "cs_")
    result = _resource(_request("GET", f"/v1/checkout/sessions/{identifier}"), "checkout.session", "cs_", identifier)
    if result.get("url") is not None:
        _hosted_url(result["url"], "checkout.stripe.com")
    return result


def expire_checkout(session_id):
    identifier = _identifier(session_id, "cs_")
    return _resource(_request("POST", f"/v1/checkout/sessions/{identifier}/expire", {},
                              idempotency_key=f"azula-expire-{identifier}"), "checkout.session", "cs_", identifier)


def find_checkout(customer_id, checkout_reference):
    """Recherche bornée d'une création dont la réponse réseau a pu être perdue."""
    customer = _identifier(customer_id, "cus_")
    reference = _company_id(checkout_reference)
    result = _request("GET", "/v1/checkout/sessions", {"customer": customer, "limit": "100"}, collection=True)
    matches = []
    for candidate in result["data"]:
        if not isinstance(candidate, dict):
            raise ProviderError()
        _resource(candidate, "checkout.session", "cs_")
        if candidate.get("customer") != customer or candidate.get("livemode") is not _mode():
            raise ProviderError()
        if candidate.get("url") is not None:
            _hosted_url(candidate["url"], "checkout.stripe.com")
        metadata = candidate.get("metadata")
        if not isinstance(metadata, dict):
            raise ProviderError()
        if metadata.get("azula_checkout_attempt") == reference:
            if candidate.get("mode") != "subscription":
                raise ProviderError()
            matches.append(candidate)
    if len(matches) > 1 or (not matches and result["has_more"]):
        raise ProviderError()
    return matches[0] if matches else None


def verify_event(raw_body, signature_header):
    """Valide les octets signés et le mode avant de transmettre un événement snapshot."""
    code = "billing_invalid_event"
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if (not isinstance(secret, str) or not re.fullmatch(r"whsec_[A-Za-z0-9]{8,256}", secret)
            or not isinstance(raw_body, bytes) or not raw_body or len(raw_body) > MAX_BODY_BYTES
            or not isinstance(signature_header, str) or len(signature_header) > 8192):
        raise ProviderError(code)
    timestamps = []
    signatures = []
    for segment in signature_header.split(","):
        name, separator, value = segment.strip().partition("=")
        if not separator:
            raise ProviderError(code)
        if name == "t":
            timestamps.append(value)
        elif name == "v1" and re.fullmatch(r"[0-9a-f]{64}", value):
            signatures.append(value)
    if len(timestamps) != 1 or not re.fullmatch(r"[0-9]{1,12}", timestamps[0]) or not signatures:
        raise ProviderError(code)
    timestamp = timestamps[0]
    if abs(time.time() - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        raise ProviderError(code)
    expected = hmac.new(secret.encode("ascii"), timestamp.encode("ascii") + b"." + raw_body, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise ProviderError(code)
    result = _json_object(raw_body, code)
    try:
        _identifier(result.get("id"), "evt_")
        if (result.get("object") != "event" or result.get("livemode") is not _mode()
                or result.get("api_version") != _version()
                or not isinstance(result.get("type"), str)
                or not re.fullmatch(r"[a-z][a-z0-9_.]{0,127}", result["type"])
                or type(result.get("created")) is not int or result["created"] < 0
                or not isinstance(result.get("data"), dict)
                or not isinstance(result["data"].get("object"), dict)):
            raise ProviderError(code)
    except ProviderError:
        raise ProviderError(code) from None
    return result
