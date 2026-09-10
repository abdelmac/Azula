"""Connexions : données synthétiques PostgreSQL, aucune banque ou API distante."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from connections.models import (
    BankAccount,
    BankTransaction,
    ExternalRequest,
    ExternalTransaction,
    Integration,
    IntegrationKey,
)
from connections.services import import_bank_csv, issue_key, parse_csv, reconcile_bank_transaction
from erp.models import Company, Customer, Invoice, Payment, Period, Product, User
from erp.services import DomainError, bootstrap_company, save_draft, validate_invoice

pytestmark = pytest.mark.django_db(transaction=True)
CSV = "external_id,date,amount,description,reference\nTX-1,2026-09-10,40.00,Payment,Order 1\nTX-2,2026-09-10,-3.25,Fee,Fee 1\n"


@pytest.fixture
def setup():
    company = Company.objects.create(name="Connexions", currency="EUR", precision=2)
    other = Company.objects.create(name="Privée", currency="EUR", precision=2)
    users = {role: User.objects.create_user(username=f"connections-{role}", company=company, role=role) for role in ("admin", "accountant", "sales", "viewer")}
    client = APIClient()
    client.force_authenticate(users["admin"])
    integration = Integration.objects.create(company=company, name="Boutique", kind="website")
    account = BankAccount.objects.create(company=company, name="Compte", currency="EUR")
    customer = Customer.objects.create(company=company, name="Client")
    return {"company": company, "other": other, "users": users, "client": client, "integration": integration, "account": account, "customer": customer}


def token_client(setup, scopes):
    key, token = issue_key(setup["company"], setup["users"]["admin"], {"integration": setup["integration"].pk, "name": "Test", "scopes": scopes, "expires_at": timezone.now() + timedelta(days=1)})
    client = APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
    return client, key, token


def validated(setup):
    bootstrap_company(setup["company"])
    Period.objects.create(company=setup["company"], name="2026", start=date(2026, 1, 1), end=date(2026, 12, 31))
    invoice = save_draft(setup["company"], setup["users"]["admin"], {"customer": setup["customer"].pk, "issue_date": "2026-09-01", "due_date": "2026-09-30", "lines": [{"description": "Article", "quantity": "1", "unit_price": "100", "tax_rate": "0"}]})
    return validate_invoice(setup["company"], setup["users"]["admin"], invoice.pk, "connections-validate")


def import_rows(setup):
    data = {"csv": CSV}
    preview = import_bank_csv(setup["company"], setup["users"]["admin"], setup["account"].pk, data)
    return import_bank_csv(setup["company"], setup["users"]["admin"], setup["account"].pk, {**data, "confirm": True, "preview_digest": preview["preview_digest"]})


@pytest.mark.parametrize("role,management,banking", [("admin", True, True), ("accountant", False, True), ("sales", False, False), ("viewer", False, False)])
def test_session_permissions(setup, role, management, banking):
    client = setup["client"]
    client.force_authenticate(setup["users"][role])
    assert client.get("/api/integrations/").status_code == (200 if management else 403)
    assert client.get("/api/integration-keys/").status_code == (200 if management else 403)
    assert client.get("/api/bank-accounts/").status_code == (200 if banking else 403)
    assert client.get("/api/bank-transactions/").status_code == (200 if banking else 403)
    assert client.post("/api/bank-accounts/", {"name": "Nouveau", "currency": "EUR"}, format="json").status_code == (201 if banking else 403)


def test_session_management_requires_csrf_and_token_cannot_replace_it(setup):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(setup["users"]["admin"])
    assert client.post("/api/integrations/", {"name": "Blocked", "kind": "website"}, format="json").status_code == 403
    external, _, _ = token_client(setup, ["catalog:read"])
    assert external.get("/api/integrations/").status_code == 401
    assert external.get("/api/products/").status_code == 401
    assert client.get("/api/external/v1/catalog/").status_code == 401


def test_key_created_once_digest_only_revocation(setup):
    response = setup["client"].post("/api/integration-keys/", {"integration": setup["integration"].pk, "name": "Web", "scopes": ["catalog:read"], "expires_at": (timezone.now() + timedelta(days=30)).isoformat()}, format="json")
    assert response.status_code == 201
    data = response.json()
    assert data["secret"].startswith("azula_") and len(data["secret"]) == 49
    assert response["Cache-Control"].startswith("no-store")
    key = IntegrationKey.objects.get(pk=data["key"]["id"])
    assert key.digest != data["secret"] and len(key.digest) == 64
    listing = setup["client"].get("/api/integration-keys/").json()
    assert data["secret"] not in str(listing) and key.digest not in str(listing)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + data["secret"])
    assert client.get("/api/external/v1/catalog/").status_code == 200
    for _ in range(2):
        assert setup["client"].post(f"/api/integration-keys/{key.pk}/revoke/", {}, format="json").status_code == 200
    assert client.get("/api/external/v1/catalog/").status_code == 401


@pytest.mark.parametrize("change", ["expired", "inactive_creator", "demoted_creator", "disabled_integration", "company_changed"])
def test_key_rechecks_current_authority(setup, change, monkeypatch):
    client, key, _ = token_client(setup, ["catalog:read"])
    if change == "expired":
        monkeypatch.setattr("connections.auth.timezone.now", lambda: key.expires_at + timedelta(seconds=1))
    elif change == "disabled_integration":
        Integration.objects.filter(pk=setup["integration"].pk).update(enabled=False)
    else:
        values = {"inactive_creator": {"is_active": False}, "demoted_creator": {"role": "viewer"}, "company_changed": {"company": setup["other"]}}[change]
        User.objects.filter(pk=setup["users"]["admin"].pk).update(**values)
    assert client.get("/api/external/v1/catalog/").status_code == 401


def test_external_scopes_isolation_and_decimal_contract(setup):
    Product.objects.create(company=setup["company"], reference="P1", name="Public", unit_price="1.234567", purchase_price="0.2", tax_rate="20")
    Product.objects.create(company=setup["other"], reference="SECRET", name="Privé", unit_price="1", tax_rate="0")
    client, _, _ = token_client(setup, ["catalog:read"])
    data = client.get("/api/external/v1/catalog/").json()
    assert data["count"] == 1 and data["results"][0]["unit_price"] == "1.234567"
    assert "purchase_price" not in data["results"][0]
    assert client.get("/api/external/v1/customers/").status_code == 403
    assert client.post("/api/external/v1/customers/", {"name": "Denied"}, format="json", HTTP_IDEMPOTENCY_KEY="denied").status_code == 403


def test_external_customer_idempotency_strict_input_and_cross_action_conflict(setup):
    client, _, _ = token_client(setup, ["customers:write", "transactions:write"])
    path = "/api/external/v1/customers/"
    assert client.post(path, {"name": "A"}, format="json").status_code == 400
    assert client.post(path, {"name": "A", "company": setup["other"].pk}, format="json", HTTP_IDEMPOTENCY_KEY="one").status_code == 400
    first = client.post(path, {"name": "API Client"}, format="json", HTTP_IDEMPOTENCY_KEY="one")
    second = client.post(path, {"name": "API Client"}, format="json", HTTP_IDEMPOTENCY_KEY="one")
    assert first.status_code == 201 and second.status_code == 200 and first.json() == second.json()
    assert second["Idempotency-Replayed"] == "true"
    assert Customer.objects.filter(company=setup["company"], name="API Client").count() == 1
    assert client.post(path, {"name": "Changed"}, format="json", HTTP_IDEMPOTENCY_KEY="one").status_code == 409
    data = {"external_id": "T1", "date": "2026-09-10", "amount": "40.00", "currency": "EUR"}
    assert client.post("/api/external/v1/transactions/", data, format="json", HTTP_IDEMPOTENCY_KEY="one").status_code == 409
    assert ExternalRequest.objects.count() == 1 and ExternalTransaction.objects.count() == 0


def test_external_invoices_remain_drafts_with_no_financial_entries(setup):
    client, _, _ = token_client(setup, ["invoices:write", "invoices:read"])
    payload = {"customer": setup["customer"].pk, "issue_date": "2026-09-01", "due_date": "2026-09-30", "document_language": "fr", "lines": [{"description": "API", "quantity": "3", "unit_price": "0.333333", "tax_rate": "20"}]}
    response = client.post("/api/external/v1/invoices/", payload, format="json", HTTP_IDEMPOTENCY_KEY="draft")
    assert response.status_code == 201
    assert response.json()["status"] == "draft" and response.json()["total"] == "1.20"
    invoice = Invoice.objects.get(pk=response.json()["id"])
    assert invoice.entries.count() == 0
    assert client.post(f"/api/invoices/{invoice.pk}/validate/", {}, format="json", HTTP_IDEMPOTENCY_KEY="validate").status_code == 401
    other_customer = Customer.objects.create(company=setup["other"], name="Privé")
    assert client.post("/api/external/v1/invoices/", {**payload, "customer": other_customer.pk}, format="json", HTTP_IDEMPOTENCY_KEY="cross").status_code == 404


def test_external_transactions_received_only_and_provider_id_duplicates(setup):
    client, _, _ = token_client(setup, ["transactions:write"])
    payload = {"external_id": "P1", "amount": "40.00", "currency": "EUR", "date": "2026-09-10", "reference": "Commande"}
    path = "/api/external/v1/transactions/"
    for key in ("transaction", "different-request"):
        response = client.post(path, payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
        assert response.status_code == 201 and response.json()["status"] == "received"
    assert ExternalTransaction.objects.count() == 1 and Payment.objects.count() == 0
    assert client.post(path, {**payload, "amount": "41.00"}, format="json", HTTP_IDEMPOTENCY_KEY="changed").status_code == 409
    assert client.post(path, {**payload, "external_id": "P2", "amount": 40.0}, format="json", HTTP_IDEMPOTENCY_KEY="float").status_code == 400
    assert client.post(path, {**payload, "external_id": "P2", "currency": "USD"}, format="json", HTTP_IDEMPOTENCY_KEY="currency").status_code == 400


def test_bank_preview_confirm_replay_and_conflicts(setup):
    path = f"/api/bank-accounts/{setup['account'].pk}/import/"
    client = setup["client"]
    preview = client.post(path, {"csv": CSV}, format="json")
    assert preview.status_code == 200 and preview.json()["total"] == "36.750000"
    assert BankTransaction.objects.count() == 0
    assert client.post(path, {"csv": CSV, "confirm": True}, format="json").status_code == 409
    data = {"csv": CSV, "confirm": True, "preview_digest": preview.json()["preview_digest"]}
    result = client.post(path, data, format="json")
    assert result.status_code == 200 and result.json()["created"] == 2
    replay = client.post(path, data, format="json")
    assert replay.json()["created"] == 0 and replay.json()["duplicates"] == 2
    assert BankTransaction.objects.count() == 2
    assert client.post(path, {"csv": CSV.replace("40.00", "41.00")}, format="json").status_code == 409


@pytest.mark.parametrize("content", [
    "external_id,date,amount,description\na,2026-09-10,NaN,x", "external_id,date,amount,description\na,2026-09-10,1e2,x",
    "external_id,date,amount,description\na,2026-09-10,0,x", "external_id,date,amount,description\na,2026-09-10,1.1234567,x",
    "external_id,date,amount,description\na,2026-09-10,1,x\na,2026-09-10,1,x", "external_id,date,amount,description\na,2026-02-30,1,x",
    "external_id,date,amount,description\na,2026-09-10,1,x,extra", "external_id,date,amount,description\na,2026-09-10,1",
    "external_id,date,amount,description,company\na,2026-09-10,1,x,1", "external_id,date,amount,description\n",
])
def test_bank_invalid_csv_rejected_atomically(setup, content):
    result = setup["client"].post(f"/api/bank-accounts/{setup['account'].pk}/import/", {"csv": content}, format="json")
    assert result.status_code == 400 and BankTransaction.objects.count() == 0


def test_csv_unicode_quotes_limits_and_negative_exactness():
    rows = parse_csv('\ufeffexternal_id,date,amount,description\nTX,2026-09-10,-0.000001,"Frais, été"')
    assert rows[0]["description"] == "Frais, été" and rows[0]["amount"] == "-0.000001"
    with pytest.raises(Exception):
        parse_csv("external_id,date,amount,description\n" + "\n".join(f"{i},2026-09-10,1,x" for i in range(501)))


def test_bank_company_isolation_account_validation_and_immutable_routes(setup):
    foreign = BankAccount.objects.create(company=setup["other"], name="Privé", currency="EUR")
    client = setup["client"]
    assert client.get("/api/bank-accounts/").json()["count"] == 1
    assert client.post(f"/api/bank-accounts/{foreign.pk}/import/", {"csv": CSV}, format="json").status_code == 404
    assert client.get(f"/api/bank-transactions/?account={foreign.pk}").status_code == 404
    for values in ({"currency": "USD"}, {"iban": "FR0000000000000000000000000"}, {"company": setup["other"].pk}):
        assert client.post("/api/bank-accounts/", {"name": "Bad", "currency": "EUR", **values}, format="json").status_code == 400
    assert client.post("/api/bank-accounts/", {"name": "IBAN", "currency": "EUR", "iban": "DE89 3704 0044 0532 0130 00", "bic": "COBADEFFXXX"}, format="json").status_code == 201
    import_rows(setup)
    item = BankTransaction.objects.first()
    assert client.patch(f"/api/bank-transactions/{item.pk}/", {"amount": "99"}, format="json").status_code == 405
    assert client.delete(f"/api/bank-transactions/{item.pk}/").status_code == 405
    assert client.patch(f"/api/bank-accounts/{setup['account'].pk}/", {"iban": "DE89370400440532013000"}, format="json").status_code == 409
    assert client.get("/api/bank-transactions/summary/?reconciled=false").json()["amount"] == "36.750000"


def test_reconcile_is_explicit_exact_atomic_and_idempotent(setup):
    invoice = validated(setup)
    import_rows(setup)
    item = BankTransaction.objects.get(external_id="TX-1")
    path = f"/api/bank-transactions/{item.pk}/reconcile/"
    client = setup["client"]
    assert client.post(path, {"invoice": invoice.pk, "confirm": False}, format="json").status_code == 400
    assert Payment.objects.count() == 0
    first = client.post(path, {"invoice": invoice.pk, "confirm": True}, format="json")
    replay = client.post(path, {"invoice": invoice.pk, "confirm": True}, format="json")
    assert first.status_code == 200 and first.json() == replay.json()
    assert Payment.objects.count() == 1 and Payment.objects.get().amount == Decimal("40")
    assert Invoice.objects.get(pk=invoice.pk).balance == Decimal("60")
    assert invoice.entries.count() == 2
    assert client.get("/api/bank-transactions/?reconciled=true").json()["count"] == 1


def test_reconcile_cross_company_negative_and_closed_period_no_side_effect(setup):
    invoice = validated(setup)
    import_rows(setup)
    positive = BankTransaction.objects.get(external_id="TX-1")
    negative = BankTransaction.objects.get(external_id="TX-2")
    with pytest.raises(DomainError, match="invalid_input"):
        reconcile_bank_transaction(setup["company"], setup["users"]["admin"], negative.pk, invoice.pk)
    other_customer = Customer.objects.create(company=setup["other"], name="Privé")
    foreign_invoice = Invoice.objects.create(company=setup["other"], customer=other_customer, issue_date=date(2026, 9, 1), due_date=date(2026, 9, 30))
    with pytest.raises(DomainError, match="not_found"):
        reconcile_bank_transaction(setup["company"], setup["users"]["admin"], positive.pk, foreign_invoice.pk)
    Period.objects.filter(company=setup["company"]).update(closed=True)
    with pytest.raises(DomainError, match="period_closed"):
        reconcile_bank_transaction(setup["company"], setup["users"]["admin"], positive.pk, invoice.pk)
    assert Payment.objects.count() == 0
    positive.refresh_from_db()
    assert positive.reconciled_at is None


def test_parallel_reconciliation_creates_one_payment(setup):
    invoice = validated(setup)
    import_rows(setup)
    item = BankTransaction.objects.get(external_id="TX-1")

    def perform(_):
        close_old_connections()
        try:
            company = Company.objects.get(pk=setup["company"].pk)
            user = User.objects.get(pk=setup["users"]["admin"].pk)
            result = reconcile_bank_transaction(company, user, item.pk, invoice.pk)
            return result.payment_id
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(perform, range(2)))
    assert results[0] == results[1] and Payment.objects.count() == 1


def test_database_guards_preserve_imports_and_company_currency(setup):
    import_rows(setup)
    item = BankTransaction.objects.get(external_id="TX-1")
    for operation in (
        lambda: BankTransaction.objects.filter(pk=item.pk).update(amount="90.00"),
        lambda: BankTransaction.objects.filter(pk=item.pk).delete(),
        lambda: Company.objects.filter(pk=setup["company"].pk).update(currency="USD"),
        lambda: Company.objects.filter(pk=setup["company"].pk).update(precision=3),
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            operation()
    item.refresh_from_db()
    assert item.amount == Decimal("40")


def test_reconciliation_reference_collision_does_not_reuse_a_payment(setup):
    from erp.services import record_payment

    invoice = validated(setup)
    import_rows(setup)
    item = BankTransaction.objects.get(external_id="TX-1")
    record_payment(setup["company"], setup["users"]["admin"], invoice.pk, "manual-payment", {"amount": "1.00", "date": "2026-09-10", "reference": f"BANKTX-{item.pk}"})
    result = reconcile_bank_transaction(setup["company"], setup["users"]["admin"], item.pk, invoice.pk)
    assert result.payment.amount == Decimal("40") and Payment.objects.count() == 2
