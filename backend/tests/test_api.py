from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, override_settings
from rest_framework.test import APIClient

from erp.models import AuditEvent, Company, Customer, Entry, Invoice, LoginAttempt, Payment, Period, Product, User
from erp.services import bootstrap_company, save_draft, validate_invoice

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def setup_api():
    company = Company.objects.create(name="Société API", currency="EUR", precision=2)
    users = {role: User.objects.create_user(username=f"api-{role}", password="Azula-test-password-7395!", company=company, role=role) for role in ("admin", "accountant", "sales", "viewer")}
    customer = Customer.objects.create(company=company, name="Client API", email="client@example.invalid")
    product = Product.objects.create(company=company, reference="TEST", name="Service", unit_price="100.00", tax_rate="20")
    period = Period.objects.create(company=company, name="2026", start=date(2026, 1, 1), end=date(2026, 12, 31))
    bootstrap_company(company)
    other = Company.objects.create(name="Autre société")
    other_customer = Customer.objects.create(company=other, name="Client privé")
    return {"company": company, "users": users, "customer": customer, "product": product, "period": period, "other": other, "other_customer": other_customer}


def api_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def draft_data(data):
    return {"customer": data["customer"].pk, "issue_date": "2026-09-07", "due_date": "2026-10-07", "document_language": "fr", "lines": [{"product": data["product"].pk, "description": "Prestation test", "quantity": "1", "unit_price": "100.00", "tax_rate": "20"}]}


def create_invoice(data):
    return save_draft(data["company"], data["users"]["sales"], draft_data(data))


def test_login_and_logout_enforce_csrf_including_anonymous(setup_api):
    client = APIClient(enforce_csrf_checks=True)
    credentials = {"username": "api-admin", "password": "Azula-test-password-7395!"}
    response = client.post("/api/auth/login/", credentials, format="json")
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    csrf = client.get("/api/auth/csrf/").json()["csrfToken"]
    response = client.post("/api/auth/login/", credentials, format="json", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.cookies["sessionid"]["httponly"]
    assert "password" not in response.json()
    assert client.get("/api/auth/me/").status_code == 200
    assert client.post("/api/auth/logout/", {}, format="json").status_code == 403
    csrf = client.get("/api/auth/csrf/").json()["csrfToken"]
    assert client.post("/api/auth/logout/", {}, format="json", HTTP_X_CSRFTOKEN=csrf).status_code == 204
    assert client.get("/api/auth/me/").status_code == 401


@override_settings(LOGIN_MAX_FAILURES=2, LOGIN_IP_MAX_FAILURES=10)
def test_login_rate_limit_persists_and_is_generic(setup_api):
    client = APIClient()
    data = {"username": "unknown-account", "password": "incorrect"}
    assert client.post("/api/auth/login/", data, format="json").json()["code"] == "invalid_credentials"
    assert client.post("/api/auth/login/", data, format="json").status_code == 401
    response = client.post("/api/auth/login/", data, format="json")
    assert response.status_code == 429
    assert response.json() == {"code": "rate_limited", "detail": "rate_limited"}
    assert LoginAttempt.objects.count() == 2
    assert all("unknown-account" not in row.key for row in LoginAttempt.objects.all())


@pytest.mark.parametrize("role,can_write", [("admin", True), ("accountant", True), ("sales", True), ("viewer", False)])
def test_customer_permissions_are_server_side(setup_api, role, can_write):
    client = api_for(setup_api["users"][role])
    response = client.post("/api/customers/", {"name": "Nouveau client"}, format="json")
    assert response.status_code == (201 if can_write else 403)
    assert client.get("/api/customers/").status_code == 200
    assert client.delete(f"/api/customers/{setup_api['customer'].pk}/").status_code == 405


@pytest.mark.parametrize("role,can_post", [("admin", True), ("accountant", True), ("sales", False), ("viewer", False)])
def test_invoice_validation_permissions(setup_api, role, can_post):
    invoice = create_invoice(setup_api)
    response = api_for(setup_api["users"][role]).post(f"/api/invoices/{invoice.pk}/validate/", {}, format="json", HTTP_IDEMPOTENCY_KEY="test-validation")
    assert response.status_code == (200 if can_post else 403)
    assert Entry.objects.count() == int(can_post)


def test_complete_api_flow_exact_amounts_idempotency_and_journal(setup_api):
    sales = api_for(setup_api["users"]["sales"])
    client_response = sales.post("/api/customers/", {"name": "Parcours complet"}, format="json")
    assert client_response.status_code == 201
    data = draft_data(setup_api)
    data["customer"] = client_response.json()["id"]
    response = sales.post("/api/invoices/", data, format="json")
    assert response.status_code == 201, response.data
    invoice_id = response.json()["id"]
    assert [response.json()[field] for field in ("net", "tax", "total")] == ["100.00", "20.00", "120.00"]
    accountant = api_for(setup_api["users"]["accountant"])
    url = f"/api/invoices/{invoice_id}/"
    response = accountant.post(url + "validate/", {}, format="json", HTTP_IDEMPOTENCY_KEY="flow-validate")
    assert response.status_code == 200, response.data
    number = response.json()["number"]
    assert accountant.post(url + "validate/", {}, format="json", HTTP_IDEMPOTENCY_KEY="flow-validate").json()["number"] == number
    payment = {"amount": "50.00", "date": "2026-09-08", "reference": "TEST-50"}
    response = accountant.post(url + "payments/", payment, format="json", HTTP_IDEMPOTENCY_KEY="flow-payment-50")
    assert response.status_code == 200, response.data
    assert response.json()["balance"] == "70.00"
    payment["amount"] = "70.00"
    assert accountant.post(url + "payments/", payment, format="json", HTTP_IDEMPOTENCY_KEY="flow-payment-70").json()["balance"] == "0.00"
    assert accountant.post(url + "payments/", payment, format="json", HTTP_IDEMPOTENCY_KEY="flow-payment-70").status_code == 200
    assert Payment.objects.count() == 2
    assert Entry.objects.count() == 3
    entries = accountant.get("/api/entries/").json()["results"]
    assert all(entry["total_debit"] == entry["total_credit"] for entry in entries)
    sale = next(entry for entry in entries if len(entry["lines"]) == 3)
    assert {(line["account_code"], Decimal(line["debit"]), Decimal(line["credit"])) for line in sale["lines"]} == {("1100", Decimal("120"), Decimal("0")), ("4000", Decimal("0"), Decimal("100")), ("2100", Decimal("0"), Decimal("20"))}
    balance = accountant.get(f"/api/trial-balance/?period={setup_api['period'].pk}").json()
    assert balance["total_debit"] == balance["total_credit"] == "240.00"


def test_cross_company_objects_filters_and_internal_fields_rejected(setup_api):
    client = api_for(setup_api["users"]["admin"])
    other_customer = setup_api["other_customer"]
    assert client.get(f"/api/customers/{other_customer.pk}/").status_code == 404
    assert client.patch(f"/api/customers/{other_customer.pk}/", {"name": "Usurpation"}, format="json").status_code == 404
    assert client.get("/api/customers/?search=privé").json()["count"] == 0
    assert client.get(f"/api/invoices/?customer={other_customer.pk}").status_code == 404
    data = draft_data(setup_api)
    data["customer"] = other_customer.pk
    assert client.post("/api/invoices/", data, format="json").status_code == 404
    for field, value in {"company": setup_api["other"].pk, "id": 998}.items():
        assert client.post("/api/customers/", {"name": "Interne", field: value}, format="json").status_code == 400
    for field, value in {"status": "validated", "number": "FAKE", "total": "0.00", "snapshot": {}}.items():
        data = draft_data(setup_api)
        data[field] = value
        assert client.post("/api/invoices/", data, format="json").status_code == 400
    assert Invoice.objects.count() == 0


def test_other_company_invoice_entry_and_period_not_exposed(setup_api):
    invoice = create_invoice(setup_api)
    validate_invoice(setup_api["company"], setup_api["users"]["admin"], invoice.pk, "isolation")
    outsider = User.objects.create_user(username="outsider", company=setup_api["other"], role="admin", password="Other-password-123!")
    client = api_for(outsider)
    assert client.get(f"/api/invoices/{invoice.pk}/").status_code == 404
    assert client.get(f"/api/entries/{Entry.objects.get().pk}/").status_code == 404
    assert client.get(f"/api/trial-balance/?period={setup_api['period'].pk}").status_code == 404
    assert client.get(f"/api/entries/?period={setup_api['period'].pk}").status_code == 404
    assert client.post(f"/api/invoices/{invoice.pk}/payments/", {"amount": "50.00", "date": "2026-09-08"}, format="json", HTTP_IDEMPOTENCY_KEY="foreign").status_code == 404


def test_validated_invoice_snapshot_and_admin_are_immutable(setup_api):
    invoice = create_invoice(setup_api)
    client = api_for(setup_api["users"]["admin"])
    url = f"/api/invoices/{invoice.pk}/"
    response = client.post(url + "validate/", {}, format="json", HTTP_IDEMPOTENCY_KEY="immutable")
    frozen = response.json()["snapshot"]
    assert client.patch(url, {"due_date": "2026-12-31"}, format="json").json()["code"] == "immutable"
    assert client.delete(url).status_code == 405
    client.patch(f"/api/customers/{setup_api['customer'].pk}/", {"name": "Nouveau nom"}, format="json")
    client.patch(f"/api/products/{setup_api['product'].pk}/", {"unit_price": "999.00"}, format="json")
    assert client.get(url).json()["snapshot"] == frozen
    assert client.get(url).json()["customer_name"] == frozen["customer"]["name"]
    request = RequestFactory().get("/admin/")
    request.user = setup_api["users"]["admin"]
    request.user.is_staff = True
    for model in (Invoice, Entry, Payment, AuditEvent):
        model_admin = admin.site._registry[model]
        assert not model_admin.has_add_permission(request)
        assert not model_admin.has_change_permission(request)
        assert not model_admin.has_delete_permission(request)


@pytest.mark.parametrize("value", [100.0, 100, "NaN", "Infinity", "1e2", "-1", "0"])
def test_invalid_payment_amounts_and_non_string_money(setup_api, value):
    invoice = create_invoice(setup_api)
    validate_invoice(setup_api["company"], setup_api["users"]["admin"], invoice.pk, "invalid-payment")
    response = api_for(setup_api["users"]["accountant"]).post(f"/api/invoices/{invoice.pk}/payments/", {"amount": value, "date": "2026-09-08"}, format="json", HTTP_IDEMPOTENCY_KEY="invalid-amount")
    assert response.status_code == 400
    assert Payment.objects.count() == 0


def test_users_permissions_password_and_last_admin(setup_api):
    viewer = api_for(setup_api["users"]["viewer"])
    assert viewer.get("/api/users/").status_code == 403
    assert viewer.get("/api/audit/").status_code == 403
    assert viewer.patch("/api/auth/me/", {"role": "admin"}, format="json").status_code == 400
    assert viewer.patch("/api/auth/me/", {"language": "ar"}, format="json").json()["language"] == "ar"
    client = api_for(setup_api["users"]["admin"])
    assert client.post("/api/users/", {"username": "weak", "password": "123", "role": "admin"}, format="json").status_code == 400
    assert client.post("/api/users/", {"username": "bypass", "password": "Stronger-Password-174!", "is_superuser": True}, format="json").status_code == 400
    response = client.post("/api/users/", {"username": "new-user", "password": "Stronger-Password-174!", "role": "viewer", "language": "tr"}, format="json")
    assert response.status_code == 201, response.data
    assert "password" not in response.json()
    new_user = User.objects.get(pk=response.json()["id"])
    assert new_user.check_password("Stronger-Password-174!")
    assert new_user.company_id == setup_api["company"].pk
    assert AuditEvent.objects.filter(action="user.created").exists()
    response = client.patch(f"/api/users/{setup_api['users']['admin'].pk}/", {"is_active": False}, format="json")
    assert response.status_code == 400


def test_pagination_is_server_bounded_and_archive_filter_works(setup_api):
    Customer.objects.bulk_create([Customer(company=setup_api["company"], name=f"Volume {index:03d}") for index in range(125)])
    client = api_for(setup_api["users"]["viewer"])
    assert len(client.get("/api/customers/").json()["results"]) == 50
    assert len(client.get("/api/customers/?page_size=9999").json()["results"]) == 100
    assert len(client.get("/api/customers/?page=3").json()["results"]) == 26
    write_client = api_for(setup_api["users"]["sales"])
    assert write_client.patch(f"/api/customers/{setup_api['customer'].pk}/", {"archived": True}, format="json").status_code == 200
    assert client.get("/api/customers/?archived=true").json()["count"] == 1
    response = write_client.post("/api/invoices/", draft_data(setup_api), format="json")
    assert response.json()["code"] == "archived_reference"


def test_invoice_list_uses_two_queries_and_frozen_customer_name(setup_api, django_assert_num_queries):
    invoice = create_invoice(setup_api)
    validate_invoice(setup_api["company"], setup_api["users"]["admin"], invoice.pk, "query-budget")
    Customer.objects.filter(pk=setup_api["customer"].pk).update(name="Nom modifié")
    client = api_for(setup_api["users"]["viewer"])
    with django_assert_num_queries(2):
        response = client.get("/api/invoices/")
    assert response.status_code == 200
    assert response.json()["results"][0]["customer_name"] == "Client API"
    assert "snapshot" not in response.json()["results"][0]
    for term in ("Client API", "Nom modifié"):
        with django_assert_num_queries(2):
            response = client.get("/api/invoices/", {"search": term})
        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert response.json()["results"][0]["id"] == invoice.pk
        assert response.json()["results"][0]["customer_name"] == "Client API"


@override_settings(ENVIRONMENT="production", ALLOW_DEMO_DATA=True)
@pytest.mark.parametrize("command", ["seed_demo", "seed_performance"])
def test_synthetic_commands_refuse_production(setup_api, command):
    with pytest.raises(CommandError):
        call_command(command, company=setup_api["company"].pk, confirm_synthetic=True)
    assert Invoice.objects.count() == 0


def test_bootstrap_refuses_existing_installation(setup_api):
    with pytest.raises(CommandError), patch("getpass.getpass") as prompt:
        call_command("bootstrap_admin", username="new", company_name="New", currency="EUR")
    prompt.assert_not_called()


def test_bootstrap_validates_password_and_explicit_currency():
    with patch("getpass.getpass", side_effect=["not-sufficient", "different"]), pytest.raises(CommandError):
        call_command("bootstrap_admin", username="initial", company_name="Initial", currency="EUR")
    assert not Company.objects.exists()
    with patch("getpass.getpass", side_effect=["Unique-Local-Test-Password-739!", "Unique-Local-Test-Password-739!"]):
        call_command("bootstrap_admin", username="initial", company_name="Initial", currency="MAD")
    user = User.objects.get(username="initial")
    assert user.company.currency == "MAD"
    assert user.role == "admin" and not user.is_superuser
    assert user.check_password("Unique-Local-Test-Password-739!")
