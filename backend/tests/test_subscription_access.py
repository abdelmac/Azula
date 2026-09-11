"""Accès par abonnement sur PostgreSQL isolé, sans paiement ni appel réseau."""

from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.contrib import admin
from django.test import RequestFactory, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from billing.access import get_access
from billing.exceptions import SubscriptionRequired
from billing.models import Subscription
from connections.models import ExternalRequest, Integration
from connections.services import external_write, issue_key
from erp.models import Company, Customer, Invoice, User

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Subscription-test-password-7295!"


@pytest.fixture
def setup(settings):
    settings.BILLING_ENABLED = True
    settings.STRIPE_LIVE_MODE = False
    company = Company.objects.create(name="Abonnements", currency="EUR", precision=2)
    other = Company.objects.create(name="Autre société", currency="EUR", precision=2)
    users = {
        role: User.objects.create_user(username=f"subscription-{role}", company=company, role=role)
        for role in ("admin", "accountant", "sales", "viewer")
    }
    customer = Customer.objects.create(company=company, name="Client conservé")
    subscription = Subscription.objects.create(company=company, status="canceled", access_until=timezone.now() - timedelta(days=1))
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(users["admin"])
    return {"company": company, "other": other, "users": users, "customer": customer, "subscription": subscription, "client": client}


def change_subscription(setup, **values):
    Subscription.objects.filter(pk=setup["subscription"].pk).update(**values)


def csrf(client):
    return client.get("/api/auth/csrf/").json()["csrfToken"]


def assert_subscription_required(response):
    assert response.status_code == 402, getattr(response, "data", None)
    assert response.json() == {"code": "subscription_required", "detail": "subscription_required"}


def test_disabled_billing_preserves_access_without_subscription_query(setup, django_assert_num_queries):
    with override_settings(BILLING_ENABLED=False):
        with django_assert_num_queries(0):
            access = get_access(setup["company"].pk)
        assert access["enabled"] is False and access["has_access"] is True
        assert setup["client"].get("/api/customers/").status_code == 200


@pytest.mark.parametrize("status,days,expected", [
    ("active", 1, True), ("trialing", 1, True),
    ("active", -1, False), ("trialing", -1, False),
    ("active", None, False), ("trialing", None, False),
    ("past_due", 1, False), ("unpaid", 1, False),
    ("canceled", 1, False), ("incomplete", 1, False), ("none", None, False),
])
def test_status_and_expiration_are_verified_on_every_request(setup, status, days, expected):
    until = timezone.now() + timedelta(days=days) if days is not None else None
    change_subscription(setup, status=status, access_until=until)
    access = get_access(setup["company"].pk)
    assert access["enabled"] is True and access["has_access"] is expected
    response = setup["client"].get("/api/customers/")
    if expected:
        assert response.status_code == 200
        change_subscription(setup, access_until=timezone.now() - timedelta(seconds=1))
        assert_subscription_required(setup["client"].get("/api/customers/"))
    else:
        assert_subscription_required(response)


def test_access_expires_at_exact_deadline(setup, monkeypatch):
    deadline = timezone.now()
    change_subscription(setup, status="active", access_until=deadline)
    monkeypatch.setattr("billing.access.timezone.now", lambda: deadline)
    assert_subscription_required(setup["client"].get("/api/customers/"))


@pytest.mark.parametrize("status", ["active", "trialing"])
def test_test_subscription_cannot_grant_live_access(setup, status):
    change_subscription(setup, status=status, livemode=False, access_until=timezone.now() + timedelta(days=1))
    assert setup["client"].get("/api/customers/").status_code == 200
    with override_settings(STRIPE_LIVE_MODE=True):
        assert_subscription_required(setup["client"].get("/api/customers/"))
        assert setup["client"].get("/api/auth/me/").json()["billing"]["has_access"] is False
        change_subscription(setup, livemode=True)
        assert setup["client"].get("/api/customers/").status_code == 200


def test_missing_subscription_is_denied_and_other_company_cannot_grant_access(setup):
    company = Company.objects.create(name="Sans abonnement")
    user = User.objects.create_user(username="subscription-missing", company=company, role="admin")
    client = APIClient()
    client.force_login(user)
    Subscription.objects.create(company=setup["other"], status="active", access_until=timezone.now() + timedelta(days=1))
    assert_subscription_required(client.get("/api/customers/"))
    assert_subscription_required(setup["client"].get("/api/customers/"))


def test_explicit_exemption_restores_company_isolation(setup):
    change_subscription(setup, exempt=True)
    hidden = Customer.objects.create(company=setup["other"], name="Client privé")
    assert get_access(setup["company"].pk)["exempt"] is True
    result = setup["client"].get("/api/customers/")
    assert result.status_code == 200
    assert [row["id"] for row in result.json()["results"]] == [setup["customer"].pk]
    assert setup["client"].get(f"/api/customers/{hidden.pk}/").status_code == 404


@pytest.mark.parametrize("role", ["admin", "accountant", "sales", "viewer"])
def test_no_erp_role_bypasses_subscription(setup, role):
    setup["client"].force_login(setup["users"][role])
    assert_subscription_required(setup["client"].get("/api/customers/"))
    me = setup["client"].get("/api/auth/me/")
    assert me.status_code == 200 and me.json()["billing"]["has_access"] is False


def test_role_and_authentication_checks_keep_precedence(setup):
    assert APIClient().get("/api/customers/").status_code == 401
    setup["client"].force_login(setup["users"]["sales"])
    denied = setup["client"].get("/api/integrations/")
    assert denied.status_code == 403 and denied.json()["code"] == "permission_denied"


@pytest.mark.parametrize("path", [
    "/api/company/", "/api/customers/", "/api/customer-prices/", "/api/products/",
    "/api/product-categories/", "/api/warehouses/", "/api/units/", "/api/invoices/",
    "/api/accounts/", "/api/journals/", "/api/periods/", "/api/entries/", "/api/audit/",
    "/api/users/", "/api/trial-balance/", "/api/dashboard/", "/api/export/?resource=customers",
    "/api/integrations/", "/api/integration-keys/", "/api/bank-accounts/",
    "/api/bank-transactions/", "/api/external-transactions/",
])
def test_business_read_routes_cannot_bypass_subscription(setup, path):
    assert_subscription_required(setup["client"].get(path))


def test_expired_subscription_prevents_mutation_without_deleting_data(setup):
    client = setup["client"]
    token = csrf(client)
    assert_subscription_required(client.post("/api/customers/", {"name": "Interdit"}, format="json", HTTP_X_CSRFTOKEN=token))
    assert_subscription_required(client.patch(f"/api/customers/{setup['customer'].pk}/", {"name": "Altéré"}, format="json", HTTP_X_CSRFTOKEN=token))
    assert_subscription_required(client.post("/api/invoices/", {}, format="json", HTTP_X_CSRFTOKEN=token))
    setup["customer"].refresh_from_db()
    assert setup["customer"].name == "Client conservé"
    assert Customer.objects.count() == 1 and Invoice.objects.count() == 0


def test_login_me_language_and_logout_remain_available_with_csrf(setup):
    user = setup["users"]["admin"]
    user.set_password(PASSWORD)
    user.save(update_fields=["password"])
    client = APIClient(enforce_csrf_checks=True)
    credentials = {"username": user.username, "password": PASSWORD}
    assert client.post("/api/auth/login/", credentials, format="json").status_code == 403
    login = client.post("/api/auth/login/", credentials, format="json", HTTP_X_CSRFTOKEN=csrf(client))
    assert login.status_code == 200
    payload = login.json()
    assert payload["billing"]["has_access"] is False
    assert payload["company"]["id"] == setup["company"].pk
    assert "password" not in payload and "stripe_customer_id" not in str(payload)
    assert login.cookies["sessionid"]["httponly"]
    assert client.get("/api/auth/me/").json()["billing"]["has_access"] is False
    assert client.patch("/api/auth/me/", {"language": "ar"}, format="json").status_code == 403
    token = csrf(client)
    language = client.patch("/api/auth/me/", {"language": "ar"}, format="json", HTTP_X_CSRFTOKEN=token)
    assert language.status_code == 200 and language.json()["language"] == "ar"
    assert client.patch("/api/auth/me/", {"language": "fr", "billing": {"exempt": True}}, format="json", HTTP_X_CSRFTOKEN=token).status_code == 400
    assert_subscription_required(client.get("/api/invoices/"))
    assert client.post("/api/auth/logout/", {}, format="json").status_code == 403
    assert client.post("/api/auth/logout/", {}, format="json", HTTP_X_CSRFTOKEN=token).status_code == 204
    assert client.get("/api/auth/me/").status_code == 401


def test_subscription_page_remains_accessible_to_expired_company(setup):
    response = setup["client"].get("/api/billing/")
    assert response.status_code == 200
    assert APIClient().get("/api/billing/").status_code == 401


def test_company_settings_cannot_assign_subscription_or_exemption(setup):
    change_subscription(setup, status="active", access_until=timezone.now() + timedelta(days=1))
    response = setup["client"].patch("/api/company/", {"exempt": True, "subscription": "active"}, format="json", HTTP_X_CSRFTOKEN=csrf(setup["client"]))
    assert response.status_code == 400
    setup["subscription"].refresh_from_db()
    assert setup["subscription"].exempt is False


def make_external_key(setup):
    integration = Integration.objects.create(company=setup["company"], name="Boutique", kind="website")
    with override_settings(BILLING_ENABLED=False):
        key, token = issue_key(setup["company"], setup["users"]["admin"], {
            "integration": integration.pk, "name": "Test", "scopes": ["catalog:read", "customers:write"],
            "expires_at": timezone.now() + timedelta(days=1),
        })
    client = APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
    return client, key


def test_external_bearer_access_and_writes_require_current_subscription(setup):
    client, _ = make_external_key(setup)
    assert_subscription_required(client.get("/api/external/v1/catalog/"))
    assert_subscription_required(client.post("/api/external/v1/customers/", {"name": "API interdit"}, format="json", HTTP_IDEMPOTENCY_KEY="subscription-denied"))
    assert Customer.objects.count() == 1 and ExternalRequest.objects.count() == 0
    change_subscription(setup, status="active", access_until=timezone.now() + timedelta(days=1))
    assert client.get("/api/external/v1/catalog/").status_code == 200
    change_subscription(setup, access_until=timezone.now() - timedelta(seconds=1))
    assert_subscription_required(client.get("/api/external/v1/catalog/"))


def test_external_write_rechecks_subscription_after_authentication(setup):
    change_subscription(setup, status="active", access_until=timezone.now() + timedelta(days=1))
    client, key = make_external_key(setup)
    assert client.get("/api/external/v1/catalog/").status_code == 200
    change_subscription(setup, status="canceled")
    operation = Mock(return_value={"id": 1})
    with pytest.raises(SubscriptionRequired):
        external_write(key, "customers:write/create", "stale-authentication", {"name": "Interdit"}, operation)
    operation.assert_not_called()
    assert ExternalRequest.objects.count() == 0


def test_invalid_external_key_fails_authentication_before_billing(setup):
    client, key = make_external_key(setup)
    key.revoked_at = timezone.now()
    key.save(update_fields=["revoked_at"])
    response = client.get("/api/external/v1/catalog/")
    assert response.status_code == 401 and response.json()["code"] == "invalid_credentials"


@pytest.mark.parametrize("model", [Company, Customer, User])
def test_admin_inspection_and_direct_querysets_do_not_bypass_subscription(setup, model):
    request = RequestFactory().get("/admin/")
    user = setup["users"]["admin"]
    user.is_staff = True
    user.is_superuser = True
    request.user = user
    model_admin = admin.site._registry[model]
    assert model_admin.has_module_permission(request) is False
    assert model_admin.has_view_permission(request) is False
    assert list(model_admin.get_queryset(request)) == []
    change_subscription(setup, exempt=True)
    assert model_admin.has_module_permission(request) is True
    assert model_admin.has_view_permission(request) is True
    expected = 4 if model is User else 1
    assert model_admin.get_queryset(request).count() == expected
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)
