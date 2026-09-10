"""Options documentaires et invariants financiers, uniquement sur PostgreSQL."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, connection, transaction
from rest_framework.test import APIClient

from erp.models import Company, Customer, Invoice, InvoiceLine, User
from erp.services import (
    DomainError,
    _calculate,
    bootstrap_company,
    configure_company,
    duplicate_invoice,
    preview_invoice,
    record_payment,
    save_draft,
    set_period,
    validate_invoice,
)


@pytest.fixture
def documents(db):
    assert connection.vendor == "postgresql"
    company = Company.objects.create(name="Documents", print_settings={"accent": "#123456", "footer": "Original"})
    actor = User.objects.create_user(username="documents-admin", company=company, role="admin")
    customer = Customer.objects.create(company=company, name="Client document")
    bootstrap_company(company)
    set_period(company, actor, {"name": "2026", "start": "2026-01-01", "end": "2026-12-31"})
    invoice = save_draft(company, actor, {
        "customer": customer.pk, "issue_date": "2026-09-01", "due_date": "2026-09-02", "document_language": "fr",
        "customer_reference": "PO-500", "document_title": "Livraison", "notes": "Fragile", "payment_terms": "30 jours", "shipping_address": "Entrepôt A",
        "lines": [{"description": "Article", "quantity": "2", "unit_price": "50", "tax_rate": "20", "discount_rate": "10"}],
    })
    return company, actor, customer, invoice


@pytest.mark.parametrize("price,quantity,discount,expected", [
    ("0.05", "1", "10", "0.05"), ("1.005", "1", "50", "0.50"),
    ("100", "2", "100", "0.00"), ("1234567890123.45", "1", "10", "1111111101111.11"),
])
def test_discount_rounds_once_after_exact_multiplication(price, quantity, discount, expected):
    line = _calculate(SimpleNamespace(precision=2), [{"description": "Article", "quantity": quantity, "unit_price": price, "tax_rate": "20", "discount_rate": discount}])[0]
    assert line["net"] == Decimal(expected)
    assert line["total"] == line["net"] + line["tax"]


@pytest.mark.parametrize("value", ["-1", "100.0001", "0.00001", "NaN", 0.5, True])
def test_invalid_discounts_rejected(value):
    with pytest.raises(DomainError, match="invalid_amount"):
        _calculate(SimpleNamespace(precision=2), [{"description": "Article", "quantity": "1", "unit_price": "10", "tax_rate": "20", "discount_rate": value}])


@pytest.mark.django_db(transaction=True)
def test_snapshot_options_discount_and_immutability(documents):
    company, actor, _, invoice = documents
    invoice = validate_invoice(company, actor, invoice.pk, "validate-doc")
    snapshot = invoice.snapshot
    assert (snapshot["net"], snapshot["tax"], snapshot["total"]) == ("90.00", "18.00", "108.00")
    assert snapshot["lines"][0]["discount_rate"] == "10.0000"
    assert snapshot["customer_reference"] == "PO-500"
    assert snapshot["shipping_address"] == "Entrepôt A"
    configure_company(company, actor, {"print_settings": {"accent": "#ffffff", "footer": "Modifié"}})
    assert preview_invoice(company, actor, invoice.pk) == snapshot
    with pytest.raises(DomainError, match="immutable"):
        save_draft(company, actor, {"notes": "Édité"}, invoice.pk)
    with pytest.raises(IntegrityError), transaction.atomic():
        InvoiceLine.objects.filter(invoice=invoice).update(discount_rate=20)


@pytest.mark.django_db(transaction=True)
def test_preview_recalculates_without_any_invoice_write(documents):
    company, actor, _, invoice = documents
    original = Invoice.objects.values().get(pk=invoice.pk)
    configure_company(company, actor, {"precision": 3})
    result = preview_invoice(company, actor, invoice.pk)
    assert result["precision"] == 3 and result["total"] == "108.000" and result["status"] == "draft"
    assert Invoice.objects.values().get(pk=invoice.pk) == original


@pytest.mark.django_db(transaction=True)
def test_duplicate_is_new_draft_idempotent_and_retains_fields(documents):
    company, actor, _, invoice = documents
    invoice = validate_invoice(company, actor, invoice.pk, "validate-doc")
    dates = {"issue_date": "2026-09-10", "due_date": "2026-10-10"}
    copy = duplicate_invoice(company, actor, invoice.pk, "duplicate-doc", dates)
    retry = duplicate_invoice(company, actor, invoice.pk, "duplicate-doc", dates)
    assert copy.pk == retry.pk != invoice.pk
    assert copy.status == "draft" and copy.snapshot == {} and copy.number == ""
    assert copy.issue_date == date(2026, 9, 10)
    assert copy.notes == invoice.notes and copy.lines.get().discount_rate == Decimal("10")
    assert copy.payments.count() == 0
    with pytest.raises(DomainError, match="idempotency_conflict"):
        duplicate_invoice(company, actor, invoice.pk, "duplicate-doc", {**dates, "due_date": "2026-11-10"})


@pytest.mark.django_db(transaction=True)
def test_duplicate_scope_archived_customer_and_viewer(documents):
    company, actor, customer, invoice = documents
    dates = {"issue_date": "2026-09-10", "due_date": "2026-10-10"}
    other = Company.objects.create(name="Autre")
    outsider = User.objects.create_user(username="outside-doc", company=other, role="admin")
    with pytest.raises(DomainError, match="not_found"):
        duplicate_invoice(other, outsider, invoice.pk, "duplicate-doc", dates)
    actor.role = "viewer"
    with pytest.raises(DomainError, match="permission_denied"):
        duplicate_invoice(company, actor, invoice.pk, "duplicate-doc", dates)
    actor.role = "admin"
    customer.archived = True
    customer.save()
    with pytest.raises(DomainError, match="archived_reference"):
        duplicate_invoice(company, actor, invoice.pk, "duplicate-doc", dates)
    assert Invoice.objects.count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("settings", [{"accent": "red;display:none"}, {"layout": "custom"}, {"show_tax": "false"}, {"logo_url": "http://example.com/a.png"}, {"logo_url": "https://user:pass@example.com/a.png"}, {"html": "<script>"}, {"footer": "x" * 2001}, []])
def test_print_options_reject_arbitrary_content(documents, settings):
    company, actor, _, _ = documents
    with pytest.raises(DomainError, match="invalid_input"):
        configure_company(company, actor, {"print_settings": settings})


@pytest.mark.django_db(transaction=True)
def test_api_discount_string_filters_and_preview_permissions(documents):
    company, actor, _, invoice = documents
    client = APIClient()
    client.force_authenticate(actor)
    response = client.patch(f"/api/invoices/{invoice.pk}/", {"lines": [{"description": "Article", "quantity": "1", "unit_price": "10", "tax_rate": "20", "discount_rate": 10}]}, format="json")
    assert response.status_code == 400
    assert client.get(f"/api/invoices/{invoice.pk}/preview/").json()["status"] == "draft"
    invoice = validate_invoice(company, actor, invoice.pk, "validate-doc")
    assert client.get("/api/invoices/?search=PO-500&payment_status=unpaid&date_from=2026-09-01&date_to=2026-09-10").json()["count"] == 1
    assert client.get("/api/invoices/?date_from=2026-10-01&date_to=2026-09-10").status_code == 400
    assert client.get("/api/invoices/?payment_status=unknown").status_code == 400
    record_payment(company, actor, invoice.pk, "paid-doc", {"amount": "108.00", "date": "2026-09-10"})
    assert client.get("/api/invoices/?payment_status=unpaid").json()["count"] == 0
    assert client.get("/api/invoices/?payment_status=settled").json()["count"] == 1
    outsider = User.objects.create_user(username="doc-outsider", company=Company.objects.create(name="Autre"), role="viewer")
    client.force_authenticate(outsider)
    assert client.get(f"/api/invoices/{invoice.pk}/preview/").status_code == 404
