"""Indicateurs et CSV sur données synthétiques, uniquement PostgreSQL."""

import csv
import io
from datetime import date
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from erp.models import Company, Customer, Product, User
from erp.reporting import ExportView
from erp.services import bootstrap_company, record_payment, save_draft, set_period, validate_invoice

pytestmark = pytest.mark.django_db


@pytest.fixture
def reporting():
    company = Company.objects.create(name="Indicateurs", currency="EUR", precision=2)
    actor = User.objects.create_user(username="report-admin", company=company, role="admin")
    customer = Customer.objects.create(company=company, name="Client original")
    bootstrap_company(company)
    set_period(company, actor, {"name": "2026", "start": "2026-01-01", "end": "2026-12-31"})
    payload = {"customer": customer.pk, "issue_date": "2026-09-01", "due_date": "2026-09-02", "lines": [{"description": "Article", "quantity": "1", "unit_price": "100", "tax_rate": "20"}]}
    invoice = save_draft(company, actor, payload)
    invoice = validate_invoice(company, actor, invoice.pk, "report-validate")
    record_payment(company, actor, invoice.pk, "report-pay-a", {"amount": "30", "date": "2026-09-03", "reference": "VIR-A"})
    record_payment(company, actor, invoice.pk, "report-pay-b", {"amount": "20", "date": "2026-09-04", "reference": "VIR-B"})
    draft = save_draft(company, actor, {**payload, "issue_date": "2026-10-01", "due_date": "2026-10-30"})
    other = Company.objects.create(name="Privée")
    Customer.objects.create(company=other, name="SECRET")
    Product.objects.create(company=other, name="SECRET", reference="SECRET", unit_price="999")
    client = APIClient()
    client.force_authenticate(actor)
    return client, company, actor, customer, invoice, draft


def test_dashboard_exact_sums_period_and_global_balances(reporting):
    client, _, _, customer, invoice, _ = reporting
    Customer.objects.filter(pk=customer.pk).update(name="Nouveau nom")
    with patch("erp.reporting.timezone.localdate", return_value=date(2026, 9, 10)):
        response = client.get("/api/dashboard/?start=2026-09-01&end=2026-09-03")
    assert response.status_code == 200, response.data
    data = response.json()
    assert data["metrics"] == {"invoiced": "120.00", "received": "30.00", "outstanding": "70.00", "overdue": "70.00"}
    assert data["counts"] == {"drafts": 0, "validated": 1, "customers": 1, "products": 0}
    assert data["overdue_invoices"] == [{"id": invoice.pk, "number": invoice.number, "customer_name": "Client original", "due_date": "2026-09-02", "balance": "70.00"}]
    with patch("erp.reporting.timezone.localdate", return_value=date(2026, 9, 10)):
        assert client.get("/api/dashboard/?start=2026-10-01").json()["metrics"] == {"invoiced": "0.00", "received": "0.00", "outstanding": "70.00", "overdue": "70.00"}


def test_dashboard_settled_invoices_leave_open_balances(reporting):
    client, company, actor, _, invoice, _ = reporting
    record_payment(company, actor, invoice.pk, "report-settle", {"amount": "70", "date": "2026-09-05"})
    response = client.get("/api/dashboard/").json()
    assert response["metrics"]["outstanding"] == response["metrics"]["overdue"] == "0.00"
    assert response["metrics"]["received"] == "120.00"
    assert response["overdue_invoices"] == []


@pytest.mark.parametrize("query", ["start=tomorrow", "end=2026-02-30", "start=2026-09-10&end=2026-09-01", "start=20260901"])
def test_report_dates_rejected(reporting, query):
    client = reporting[0]
    assert client.get(f"/api/dashboard/?{query}").status_code == 400
    assert client.get(f"/api/export/?resource=invoices&{query}").status_code == 400


def csv_rows(response):
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Cache-Control"] == "no-store, private"
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))


def test_exports_isolate_company_preserve_frozen_name_currency_and_decimals(reporting):
    client, company, _, customer, invoice, draft = reporting
    Customer.objects.filter(pk=customer.pk).update(name="Nouveau nom")
    rows = csv_rows(client.get("/api/export/?resource=invoices", HTTP_ACCEPT="text/csv"))
    assert len(rows) == 2
    assert rows[0]["customer_label"] == "Client original"
    assert rows[1]["customer_label"] == "Nouveau nom"
    assert all(row["effective_currency"] == "EUR" for row in rows)
    assert rows[0]["total"] == "120.000000"
    assert [row["id"] for row in csv_rows(client.get("/api/export/?resource=invoices&status=draft"))] == [str(draft.pk)]
    assert [row["id"] for row in csv_rows(client.get("/api/export/?resource=invoices&search=original"))] == [str(invoice.pk)]
    assert csv_rows(client.get("/api/export/?resource=products")) == []
    product = Product.objects.create(company=company, reference="PRECISE", name="Article", unit_price="1234567890123456.123456")
    assert csv_rows(client.get("/api/export/?resource=products"))[0]["unit_price"] == str(product.unit_price)
    assert len(csv_rows(client.get("/api/export/?resource=customers"))) == 1


@pytest.mark.parametrize("name", ["=1+1", " +SUM(1)", "@external", "-1+2", "\tformula"])
def test_export_neutralizes_spreadsheet_formulas(reporting, name):
    client, _, _, customer, _, _ = reporting
    Customer.objects.filter(pk=customer.pk).update(name=name)
    assert csv_rows(client.get("/api/export/?resource=customers"))[0]["name"] == "'" + name


def test_export_permissions_filters_and_limit(reporting):
    client, company, actor, _, _, _ = reporting
    assert APIClient().get("/api/export/?resource=customers").status_code == 401
    assert APIClient().get("/api/dashboard/").status_code == 401
    for query in ("resource=unknown", "resource=customers&archived=maybe", "resource=invoices&status=deleted", "resource=payments&archived=true", "resource=customers&search=" + "x" * 129):
        assert client.get("/api/export/?" + query).status_code == 400
    with patch.object(ExportView, "limit", 1):
        assert client.get("/api/export/?resource=invoices").json()["code"] == "export_limit"
    actor.role = "viewer"
    actor.save(update_fields=["role"])
    client.force_authenticate(User.objects.get(pk=actor.pk))
    assert client.get("/api/export/?resource=payments").status_code == 403
    assert client.get("/api/export/?resource=customers").status_code == 200
    assert client.get("/api/dashboard/").status_code == 200
    assert Customer.objects.filter(company=company).count() == 1
