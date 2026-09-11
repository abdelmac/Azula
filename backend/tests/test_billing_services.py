"""Abonnements sur PostgreSQL jetable, prestataire Stripe entièrement simulé."""

import hashlib
import hmac
import json
import time
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from rest_framework.test import APIClient

from billing import provider, services
from billing.access import get_access
from billing.exceptions import BillingError
from billing.models import CheckoutAttempt, Plan, Subscription, WebhookEvent
from erp.models import AuditEvent, Company, Invoice, Payment, User

pytestmark = pytest.mark.django_db(transaction=True)
WEBHOOK_SECRET = "whsec_syntheticServiceTestSecret123456"


def price_data(identifier="price_monthly", **changes):
    return {"id": identifier, "object": "price", "active": True, "livemode": False,
            "currency": "eur", "unit_amount": 2500, "unit_amount_decimal": "2500",
            "recurring": {"interval": "month", "interval_count": 1, "usage_type": "licensed"},
            "billing_scheme": "per_unit", "transform_quantity": None, "custom_unit_amount": None,
            "tax_behavior": "inclusive"} | changes


@pytest.fixture
def billing(settings, monkeypatch):
    settings.BILLING_ENABLED = True
    settings.BILLING_PUBLIC_URL = "https://erp.example"
    settings.STRIPE_SECRET_KEY = "sk_test_fake0000"
    settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET
    settings.STRIPE_LIVE_MODE = False
    settings.STRIPE_API_VERSION = provider.SUPPORTED_API_VERSION
    instant = timezone.now().replace(microsecond=0)
    monkeypatch.setattr(timezone, "now", lambda: instant)
    company = Company.objects.create(name="Société abonnement", email="billing@example.test")
    other = Company.objects.create(name="Autre société")
    users = {role: User.objects.create_user(username=f"subscription-{role}", company=company, role=role)
             for role in ("admin", "accountant", "sales", "viewer")}
    other_user = User.objects.create_user(username="other-subscription-admin", company=other, role="admin")
    client = APIClient()
    client.force_authenticate(users["admin"])
    plan = Plan.objects.create(code="monthly", name="Mensuel synthétique", stripe_price_id="price_monthly",
                               amount=Decimal("25"), currency="EUR", precision=2, interval="month", trial_days=14)
    sessions = {}
    subscriptions = {}

    def customer(company_id, name, email, idempotency_key):
        return {"id": f"cus_company{company_id}", "object": "customer", "livemode": False}

    def checkout(customer_id, price_id, company_id, success_url, cancel_url, idempotency_key, **options):
        reference = options["checkout_reference"]
        result = {"id": f"cs_test_attempt{reference}", "object": "checkout.session", "livemode": False,
                  "mode": "subscription", "customer": customer_id, "subscription": None,
                  "status": "open", "expires_at": options["expires_at"],
                  "url": f"https://checkout.stripe.com/c/pay/attempt{reference}",
                  "metadata": {"azula_company_id": str(company_id), "azula_checkout_attempt": reference}}
        sessions[result["id"]] = result
        return deepcopy(result)

    mocks = {
        "create_customer": Mock(side_effect=customer), "create_checkout": Mock(side_effect=checkout),
        "retrieve_price": Mock(side_effect=lambda identifier: price_data(identifier)),
        "retrieve_checkout": Mock(side_effect=lambda identifier: deepcopy(sessions[identifier])),
        "retrieve_subscription": Mock(side_effect=lambda identifier: deepcopy(subscriptions[identifier])),
        "find_checkout": Mock(return_value=None),
        "create_portal": Mock(return_value={"url": "https://billing.stripe.com/p/session/synthetic"}),
        "expire_checkout": Mock(side_effect=AssertionError("unexpected_expiration_mutation")),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(provider, name, mock)
    monkeypatch.setattr(provider, "HTTPSConnection", Mock(side_effect=AssertionError("network_forbidden")))
    return {"company": company, "other": other, "users": users, "other_user": other_user,
            "client": client, "plan": plan, "now": instant, "mocks": mocks,
            "sessions": sessions, "subscriptions": subscriptions}


def post_checkout(billing, key="request-key-0001", **payload):
    return billing["client"].post("/api/billing/checkout/", {"plan_code": billing["plan"].code, **payload},
                                  format="json", HTTP_IDEMPOTENCY_KEY=key)


def known_subscription(billing, **changes):
    return Subscription.objects.create(company=billing["company"], plan=billing["plan"],
        **({"stripe_customer_id": f"cus_company{billing['company'].pk}", "stripe_subscription_id": "sub_known",
            "status": "active", "access_until": billing["now"] + timedelta(days=30),
            "current_period_end": billing["now"] + timedelta(days=30), "livemode": False} | changes))


def remote_subscription(billing, subscription, **changes):
    identifier = changes.get("id", subscription.stripe_subscription_id or "sub_known")
    end = int((billing["now"] + timedelta(days=30)).timestamp())
    return {"id": identifier, "object": "subscription", "livemode": False, "status": "active",
        "customer": subscription.stripe_customer_id, "metadata": {"azula_company_id": str(subscription.company_id)},
        "items": {"has_more": False, "data": [{"id": "si_one", "quantity": 1,
            "current_period_start": int(billing["now"].timestamp()), "current_period_end": end,
            "price": price_data(billing["plan"].stripe_price_id)}]},
        "trial_start": None, "trial_end": None, "cancel_at_period_end": False,
        "latest_invoice": {"id": "in_paid", "object": "invoice", "status": "paid", "livemode": False,
            "amount_remaining": 0, "customer": subscription.stripe_customer_id,
            "parent": {"type": "subscription_details", "subscription_details": {"subscription": identifier}}},
        **changes}


def signed_event(billing, subscription, *, event_id="evt_synthetic", kind="customer.subscription.updated", obj=None,
                 livemode=False, created=None):
    value = {"id": event_id, "object": "event", "api_version": provider.SUPPORTED_API_VERSION,
        "created": created or int(billing["now"].timestamp()), "livemode": livemode, "type": kind,
        "data": {"object": obj or {"id": subscription.stripe_subscription_id, "object": "subscription",
                                  "customer": subscription.stripe_customer_id}}}
    body = json.dumps(value, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    digest = hmac.new(WEBHOOK_SECRET.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return body, f"t={timestamp},v1={digest}"


def deliver(billing, subscription, **options):
    body, signature = signed_event(billing, subscription, **options)
    return APIClient(enforce_csrf_checks=True).post("/api/billing/webhook/", body,
        content_type="application/json", HTTP_STRIPE_SIGNATURE=signature)


@pytest.mark.parametrize("role", ["accountant", "sales", "viewer"])
def test_checkout_and_portal_require_company_admin(billing, role):
    billing["client"].force_authenticate(billing["users"][role])
    assert post_checkout(billing).status_code == 403
    assert billing["client"].post("/api/billing/portal/", {}, format="json").status_code == 403
    for mock in billing["mocks"].values():
        mock.assert_not_called()


def test_session_csrf_is_required_and_authenticated_token_must_match(billing):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(billing["users"]["admin"])
    assert client.post("/api/billing/checkout/", {"plan_code": "monthly"}, format="json",
                       HTTP_IDEMPOTENCY_KEY="csrf-test-request").status_code == 403
    client.get("/api/auth/csrf/")
    response = client.post("/api/billing/checkout/", {"plan_code": "monthly"}, format="json",
        HTTP_IDEMPOTENCY_KEY="csrf-test-request", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert response.status_code == 200


def test_checkout_double_click_reuses_one_session_even_with_new_key(billing):
    first = post_checkout(billing)
    second = post_checkout(billing)
    third = post_checkout(billing, key="request-key-0002")
    assert first.status_code == second.status_code == third.status_code == 200
    assert first.json() == second.json() == third.json()
    assert CheckoutAttempt.objects.count() == Subscription.objects.count() == 1
    billing["mocks"]["create_checkout"].assert_called_once()
    billing["mocks"]["create_customer"].assert_called_once()
    assert not Payment.objects.exists() and not Invoice.objects.exists()


def test_checkout_passes_only_configured_price_company_and_return_urls(billing):
    assert post_checkout(billing).status_code == 200
    args = billing["mocks"]["create_checkout"].call_args
    attempt = CheckoutAttempt.objects.get()
    assert args.args[:5] == (f"cus_company{billing['company'].pk}", "price_monthly", billing["company"].pk,
                             "https://erp.example/subscription?checkout=success",
                             "https://erp.example/subscription?checkout=cancelled")
    assert args.kwargs == {"trial_days": 14, "expires_at": int(attempt.expires_at.timestamp()),
                           "checkout_reference": str(attempt.pk)}
    assert len(attempt.key_digest) == 64 and attempt.key_digest != "request-key-0001"
    assert get_access(billing["company"].pk)["has_access"] is False


@pytest.mark.parametrize("extra", [
    {"amount": "0.01"}, {"price_id": "price_other"}, {"company": 999},
    {"customer_id": "cus_other"}, {"success_url": "https://evil.example/"}, {"trial_days": 90},
])
def test_checkout_rejects_browser_supplied_financial_arguments(billing, extra):
    assert post_checkout(billing, **extra).status_code == 400
    assert not CheckoutAttempt.objects.exists()
    billing["mocks"]["create_checkout"].assert_not_called()


def test_lost_customer_response_retries_same_arguments_after_company_edit(billing):
    create = billing["mocks"]["create_customer"]
    normal = create.side_effect
    create.side_effect = provider.ProviderError()
    assert post_checkout(billing).status_code == 503
    first_arguments = create.call_args
    assert CheckoutAttempt.objects.count() == 1
    assert not Subscription.objects.get().stripe_customer_id
    Company.objects.filter(pk=billing["company"].pk).update(name="Nom modifié", email="changed@example.test")
    create.side_effect = normal
    assert post_checkout(billing).status_code == 200
    assert create.call_args == first_arguments


def test_lost_checkout_response_retries_exact_reserved_request(billing, settings):
    create = billing["mocks"]["create_checkout"]
    normal = create.side_effect
    create.side_effect = provider.ProviderError()
    assert post_checkout(billing).status_code == 503
    first_arguments = create.call_args
    attempt = CheckoutAttempt.objects.get()
    assert attempt.status == "pending" and not attempt.stripe_session_id
    assert Subscription.objects.get().stripe_customer_id
    settings.BILLING_PUBLIC_URL = "https://new.example"
    create.side_effect = normal
    assert post_checkout(billing).status_code == 200
    assert create.call_args == first_arguments
    billing["mocks"]["create_customer"].assert_called_once()


def expired_pending(billing):
    subscription = known_subscription(billing, stripe_subscription_id="", status="none", access_until=None)
    attempt = CheckoutAttempt.objects.create(company=billing["company"], plan=billing["plan"],
        key_digest="a" * 64, expires_at=billing["now"] - timedelta(seconds=1),
        return_url="https://erp.example", trial_days=14)
    return subscription, attempt


def test_expired_ambiguous_checkout_absence_expires_only_local_reservation(billing):
    _, attempt = expired_pending(billing)
    services.recover_checkout(billing["company"].pk, billing["users"]["admin"])
    attempt.refresh_from_db()
    assert attempt.status == "expired"
    billing["mocks"]["find_checkout"].assert_called_once_with(f"cus_company{billing['company'].pk}", str(attempt.pk))
    billing["mocks"]["create_checkout"].assert_not_called()
    assert get_access(billing["company"].pk)["has_access"] is False


def test_expired_ambiguous_checkout_completed_session_recovers_paid_access(billing):
    subscription, attempt = expired_pending(billing)
    session = {"id": "cs_test_recovered", "customer": subscription.stripe_customer_id, "mode": "subscription",
        "status": "complete", "subscription": "sub_recovered", "livemode": False,
        "metadata": {"azula_company_id": str(subscription.company_id), "azula_checkout_attempt": str(attempt.pk)}}
    billing["mocks"]["find_checkout"].return_value = session
    billing["sessions"][session["id"]] = session
    billing["subscriptions"]["sub_recovered"] = remote_subscription(billing, subscription, id="sub_recovered")
    services.recover_checkout(subscription.company_id, billing["users"]["admin"])
    subscription.refresh_from_db()
    attempt.refresh_from_db()
    assert attempt.status == "complete" and subscription.stripe_subscription_id == "sub_recovered"
    assert get_access(subscription.company_id)["has_access"] is True
    billing["mocks"]["create_checkout"].assert_not_called()


def test_uncertain_lookup_preserves_pending_reservation(billing):
    subscription, attempt = expired_pending(billing)
    billing["mocks"]["find_checkout"].side_effect = provider.ProviderError()
    with pytest.raises(BillingError, match="billing_unavailable"):
        services.recover_checkout(subscription.company_id, billing["users"]["admin"])
    attempt.refresh_from_db()
    assert attempt.status == "pending"


@pytest.mark.parametrize("configuration", ["disabled", "missing_key", "missing_webhook"])
def test_disabled_or_unconfigured_checkout_never_contacts_stripe(billing, settings, configuration):
    if configuration == "disabled":
        settings.BILLING_ENABLED = False
    elif configuration == "missing_key":
        settings.STRIPE_SECRET_KEY = ""
    else:
        settings.STRIPE_WEBHOOK_SECRET = ""
    assert post_checkout(billing).status_code == 503
    assert not CheckoutAttempt.objects.exists()
    for mock in billing["mocks"].values():
        mock.assert_not_called()


def test_api_rejects_webhook_without_valid_raw_body_signature(billing):
    subscription = known_subscription(billing)
    body, signature = signed_event(billing, subscription)
    client = APIClient()
    assert client.post("/api/billing/webhook/", body, content_type="application/json").status_code == 400
    assert client.post("/api/billing/webhook/", body + b" ", content_type="application/json",
                       HTTP_STRIPE_SIGNATURE=signature).status_code == 400
    billing["mocks"]["retrieve_subscription"].assert_not_called()
    assert not WebhookEvent.objects.exists()


def test_signed_test_event_cannot_grant_live_mode_access(billing, settings):
    subscription = known_subscription(billing)
    settings.STRIPE_LIVE_MODE = True
    settings.STRIPE_SECRET_KEY = "sk_live_fake0000"
    assert deliver(billing, subscription, livemode=False).status_code == 400
    assert get_access(subscription.company_id)["has_access"] is False
    assert not WebhookEvent.objects.exists()
    billing["mocks"]["retrieve_subscription"].assert_not_called()


def test_paid_canonical_invoice_grants_access_without_business_payment(billing):
    subscription = known_subscription(billing, access_until=None, exempt=True)
    billing["subscriptions"][subscription.stripe_subscription_id] = remote_subscription(billing, subscription)
    assert deliver(billing, subscription).status_code == 200
    subscription.refresh_from_db()
    assert subscription.access_until == subscription.current_period_end == billing["now"] + timedelta(days=30)
    assert subscription.exempt is False and get_access(subscription.company_id)["has_access"] is True
    assert not Payment.objects.exists() and not Invoice.objects.exists()


@pytest.mark.parametrize("invoice_changes", [
    {"status": "open"}, {"amount_remaining": 1}, {"amount_remaining": False},
    {"customer": "cus_other"}, {"parent": {"type": "quote_details", "subscription_details": {"subscription": "sub_known"}}},
    {"parent": {"type": "subscription_details", "subscription_details": {"subscription": "sub_other"}}},
])
def test_unpaid_or_wrong_invoice_does_not_grant_access(billing, invoice_changes):
    subscription = known_subscription(billing, access_until=None)
    remote = remote_subscription(billing, subscription)
    remote["latest_invoice"].update(invoice_changes)
    billing["subscriptions"][subscription.stripe_subscription_id] = remote
    response = deliver(billing, subscription)
    assert response.status_code in {200, 400}
    assert get_access(subscription.company_id)["has_access"] is False


@pytest.mark.parametrize("status", ["past_due", "unpaid", "canceled", "incomplete_expired", "paused"])
def test_unpaid_or_ended_subscription_revokes_access(billing, status):
    subscription = known_subscription(billing)
    billing["subscriptions"][subscription.stripe_subscription_id] = remote_subscription(billing, subscription, status=status)
    assert deliver(billing, subscription).status_code == 200
    subscription.refresh_from_db()
    assert subscription.status == status and subscription.access_until is None
    assert get_access(subscription.company_id)["has_access"] is False


def test_cancel_at_period_end_preserves_only_paid_period(billing, monkeypatch):
    subscription = known_subscription(billing)
    billing["subscriptions"][subscription.stripe_subscription_id] = remote_subscription(billing, subscription, cancel_at_period_end=True)
    assert deliver(billing, subscription).status_code == 200
    subscription.refresh_from_db()
    assert subscription.cancel_at_period_end and get_access(subscription.company_id)["has_access"] is True
    monkeypatch.setattr(timezone, "now", lambda: subscription.current_period_end)
    assert get_access(subscription.company_id)["has_access"] is False


def test_late_paid_event_rechecks_canceled_canonical_subscription(billing):
    subscription = known_subscription(billing)
    billing["subscriptions"][subscription.stripe_subscription_id] = remote_subscription(billing, subscription, status="canceled")
    invoice = remote_subscription(billing, subscription)["latest_invoice"]
    assert deliver(billing, subscription, kind="invoice.paid", obj=invoice,
                   created=int((billing["now"] - timedelta(days=10)).timestamp())).status_code == 200
    assert get_access(subscription.company_id)["has_access"] is False
    subscription.refresh_from_db()
    assert subscription.status == "canceled"


def test_webhook_duplicate_is_idempotent_and_changed_body_rejected(billing):
    subscription = known_subscription(billing)
    billing["subscriptions"][subscription.stripe_subscription_id] = remote_subscription(billing, subscription)
    for _ in range(2):
        assert deliver(billing, subscription).status_code == 200
    assert WebhookEvent.objects.count() == 1
    assert AuditEvent.objects.filter(action="subscription.synchronized").count() == 1
    billing["mocks"]["retrieve_subscription"].assert_called_once()
    assert deliver(billing, subscription, kind="customer.subscription.deleted").status_code == 400
    assert WebhookEvent.objects.count() == 1


def test_failed_synchronization_rolls_back_and_same_event_can_retry(billing):
    subscription = known_subscription(billing)
    remote = remote_subscription(billing, subscription)
    remote["items"]["data"][0]["current_period_end"] = "invalid"
    billing["subscriptions"][subscription.stripe_subscription_id] = remote
    assert deliver(billing, subscription).status_code == 400
    assert not WebhookEvent.objects.exists() and not AuditEvent.objects.filter(action="subscription.synchronized").exists()
    subscription.refresh_from_db()
    assert subscription.access_until == billing["now"] + timedelta(days=30)
    billing["subscriptions"][subscription.stripe_subscription_id] = remote_subscription(billing, subscription)
    assert deliver(billing, subscription).status_code == 200
    assert WebhookEvent.objects.count() == 1


@pytest.mark.parametrize("changes", [{"customer": "cus_other"}, {"metadata": {"azula_company_id": "999999"}}])
def test_remote_subscription_cannot_cross_company_boundary(billing, changes):
    subscription = known_subscription(billing, access_until=None)
    billing["subscriptions"][subscription.stripe_subscription_id] = remote_subscription(billing, subscription, **changes)
    assert deliver(billing, subscription).status_code == 400
    assert get_access(subscription.company_id)["has_access"] is False
    assert not WebhookEvent.objects.exists()


def test_unknown_customer_event_is_acknowledged_without_tenant_creation(billing):
    subscription = known_subscription(billing)
    before = Subscription.objects.count()
    assert deliver(billing, subscription, obj={"id": "sub_unknown", "customer": "cus_unknown"}).status_code == 200
    assert Subscription.objects.count() == before and not WebhookEvent.objects.exists()
    billing["mocks"]["retrieve_subscription"].assert_not_called()


def test_new_subscription_requires_completed_bound_checkout(billing):
    subscription = known_subscription(billing, stripe_subscription_id="", status="none", access_until=None)
    billing["subscriptions"]["sub_unbound"] = remote_subscription(billing, subscription, id="sub_unbound")
    response = deliver(billing, subscription, obj={"id": "sub_unbound", "customer": subscription.stripe_customer_id})
    assert response.status_code == 503
    assert get_access(subscription.company_id)["has_access"] is False and not WebhookEvent.objects.exists()


def test_trial_is_limited_and_cannot_be_reused_or_extended(billing):
    assert post_checkout(billing).status_code == 200
    subscription = Subscription.objects.get(company=billing["company"])
    attempt = CheckoutAttempt.objects.get()
    session = billing["sessions"][attempt.stripe_session_id]
    session.update(status="complete", subscription="sub_trial")
    trial_end = billing["now"] + timedelta(days=14)
    remote = remote_subscription(billing, subscription, id="sub_trial", status="trialing",
        trial_start=int(billing["now"].timestamp()), trial_end=int(trial_end.timestamp()), latest_invoice=None)
    billing["subscriptions"]["sub_trial"] = remote
    assert deliver(billing, subscription, obj=session, kind="checkout.session.completed").status_code == 200
    subscription.refresh_from_db()
    assert subscription.trial_used and subscription.access_until == trial_end
    assert billing["client"].get("/api/billing/").json()["plans"][0]["trial_days"] == 0
    remote["trial_end"] += 86400
    assert deliver(billing, subscription, event_id="evt_extend_trial").status_code == 400
    subscription.refresh_from_db()
    assert subscription.trial_end == trial_end


def test_trial_cannot_exceed_checkout_authorized_duration(billing):
    assert post_checkout(billing).status_code == 200
    subscription = Subscription.objects.get()
    attempt = CheckoutAttempt.objects.get()
    session = billing["sessions"][attempt.stripe_session_id]
    session.update(status="complete", subscription="sub_long_trial")
    billing["subscriptions"]["sub_long_trial"] = remote_subscription(billing, subscription, id="sub_long_trial",
        status="trialing", trial_start=int(billing["now"].timestamp()),
        trial_end=int((billing["now"] + timedelta(days=15)).timestamp()))
    assert deliver(billing, subscription, obj=session, kind="checkout.session.completed").status_code == 400
    assert get_access(subscription.company_id)["has_access"] is False
    attempt.refresh_from_db()
    assert attempt.status == "open"


def test_portal_always_uses_authenticated_company_customer(billing):
    subscription = known_subscription(billing)
    assert billing["client"].post("/api/billing/portal/", {"customer_id": "cus_other"}, format="json").status_code == 400
    assert billing["client"].post("/api/billing/portal/", {}, format="json").status_code == 200
    billing["mocks"]["create_portal"].assert_called_once_with(subscription.stripe_customer_id, "https://erp.example/subscription")
    billing["client"].force_authenticate(billing["other_user"])
    assert billing["client"].post("/api/billing/portal/", {}, format="json").status_code == 400
    assert billing["client"].get("/api/billing/").json()["subscription"] is None


@pytest.mark.parametrize("plan_change", ["missing", "inactive", "wrong_mode", "changed_amount"])
def test_missing_or_invalid_plan_never_creates_checkout(billing, plan_change):
    if plan_change == "missing":
        billing["plan"].delete()
    elif plan_change == "inactive":
        Plan.objects.filter(pk=billing["plan"].pk).update(active=False)
    elif plan_change == "wrong_mode":
        Plan.objects.filter(pk=billing["plan"].pk).update(livemode=True)
    else:
        billing["mocks"]["retrieve_price"].side_effect = lambda identifier: price_data(identifier, unit_amount=2600, unit_amount_decimal="2600")
    response = billing["client"].post("/api/billing/checkout/", {"plan_code": "monthly"}, format="json", HTTP_IDEMPOTENCY_KEY="invalid-plan-key")
    assert response.status_code == 400 and response.json()["code"] == "billing_invalid_plan"
    billing["mocks"]["create_checkout"].assert_not_called()


@pytest.mark.parametrize("currency,minor,expected,precision", [
    ("eur", 1234, "12.34", 2), ("jpy", 1234, "1234", 0), ("kwd", 1234, "1.234", 3),
])
def test_operator_imports_exact_existing_stripe_tariff(billing, currency, minor, expected, precision):
    billing["mocks"]["retrieve_price"].side_effect = lambda identifier: price_data(identifier, currency=currency,
        unit_amount=minor, unit_amount_decimal=str(minor))
    call_command("configure_subscription_plan", code="imported", price_id="price_imported", name="Prix fourni",
                 trial_days=0, stdout=StringIO())
    plan = Plan.objects.get(code="imported")
    assert plan.amount == Decimal(expected) and plan.precision == precision
    assert plan.currency == currency.upper() and plan.stripe_price_id == "price_imported"
    billing["mocks"]["create_checkout"].assert_not_called()
    billing["mocks"]["create_customer"].assert_not_called()


@pytest.mark.parametrize("changes", [
    {"unit_amount": 0}, {"unit_amount": True}, {"unit_amount_decimal": "2500.1"}, {"currency": "isk"},
    {"currency": "ugx"}, {"active": False}, {"livemode": True},
    {"recurring": {"interval": "month", "interval_count": True, "usage_type": "licensed"}},
    {"recurring": {"interval": "month", "interval_count": 1, "usage_type": "metered"}},
])
def test_operator_rejects_incompatible_provider_price(billing, changes):
    billing["mocks"]["retrieve_price"].side_effect = lambda identifier: price_data(identifier, **changes)
    with pytest.raises(CommandError):
        call_command("configure_subscription_plan", code="bad", price_id="price_bad", name="Refusé", stdout=StringIO())
    assert not Plan.objects.filter(code="bad").exists()


def test_operator_cannot_replace_historical_price_for_existing_code(billing):
    with pytest.raises(CommandError):
        call_command("configure_subscription_plan", code="monthly", price_id="price_replacement", name="Nouveau", stdout=StringIO())
    billing["plan"].refresh_from_db()
    assert billing["plan"].stripe_price_id == "price_monthly"


def test_checkout_requires_idempotency_key_and_conflicting_plan_is_rejected(billing):
    response = billing["client"].post("/api/billing/checkout/", {"plan_code": "monthly"}, format="json")
    assert response.status_code == 400 and response.json()["code"] == "billing_idempotency_required"
    assert not CheckoutAttempt.objects.exists()
    assert post_checkout(billing).status_code == 200
    Plan.objects.create(code="alternative", name="Autre", stripe_price_id="price_alternative", amount=25,
                        currency="EUR", precision=2, interval="month")
    response = post_checkout(billing, plan_code="alternative")
    assert response.status_code == 409 and response.json()["code"] == "idempotency_conflict"
    billing["mocks"]["create_checkout"].assert_called_once()


def test_returning_subscriber_receives_no_second_trial(billing):
    known_subscription(billing, status="canceled", trial_used=True, access_until=None,
        trial_end=billing["now"] - timedelta(days=30))
    assert post_checkout(billing).status_code == 200
    assert billing["mocks"]["create_checkout"].call_args.kwargs["trial_days"] == 0
    assert CheckoutAttempt.objects.get().trial_days == 0


def test_service_reloads_administrator_before_contacting_provider(billing):
    stale_actor = billing["users"]["admin"]
    User.objects.filter(pk=stale_actor.pk).update(role="viewer")
    with pytest.raises(BillingError, match="permission_denied"):
        services.checkout(stale_actor, "monthly", "stale-admin-request")
    for mock in billing["mocks"].values():
        mock.assert_not_called()


def test_portal_rejects_customer_in_different_stripe_mode(billing):
    known_subscription(billing, livemode=True)
    response = billing["client"].post("/api/billing/portal/", {}, format="json")
    assert response.status_code == 409 and response.json()["code"] == "billing_mode_conflict"
    billing["mocks"]["create_portal"].assert_not_called()


def test_boolean_item_quantity_is_not_one_subscription_seat(billing):
    subscription = known_subscription(billing, access_until=None)
    remote = remote_subscription(billing, subscription)
    remote["items"]["data"][0]["quantity"] = True
    billing["subscriptions"][subscription.stripe_subscription_id] = remote
    assert deliver(billing, subscription).status_code == 400
    assert get_access(subscription.company_id)["has_access"] is False
    assert not WebhookEvent.objects.exists()
