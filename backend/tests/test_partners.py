"""CRM et tarifs : contrôles réels sur PostgreSQL jetable uniquement."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from erp.models import AuditEvent, Company, Customer, CustomerPrice, Period, Product, User
from erp.services import bootstrap_company, record_payment, save_draft, validate_invoice

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def partners():
    company = Company.objects.create(name="CRM test")
    other = Company.objects.create(name="CRM privé")
    user = User.objects.create_user(username="crm-admin", company=company, role="admin")
    customer = Customer.objects.create(company=company, name="Client CRM", reference="C-1", default_discount_rate=Decimal("7.1250"))
    product = Product.objects.create(company=company, name="Article CRM", reference="P-1", unit_price=Decimal("12.123456"), tax_rate=Decimal("5.5"))
    client = APIClient()
    client.force_authenticate(user)
    return company, other, user, customer, product, client


def test_customer_contact_commercial_fields_and_unique_reference(partners):
    company, other, user, customer, product, client = partners
    payload = {"name": "Client complet", "reference": "C-2", "legal_name": "SARL Exemple", "latin_name": "Example", "contact_name": "Responsable", "phone": "+33 100000001", "phone_alt": "+33 100000002", "mobile": "+33 600000000", "fax": "+33 100000003", "website": "https://example.com", "address": "Rue exemple", "city": "Paris", "region": "Île-de-France", "country": "FR", "postal_code": "75001", "shipping_address": "Dépôt 2", "group_name": "Grossistes", "payment_terms_days": 30, "default_discount_rate": "2.1234", "credit_limit": "123456789.123456", "bank_name": "Banque test", "iban": "FR1420041010050500013M02606", "bic": "BNPAFRPP", "notes": "Livrer le matin", "custom_fields": {"Tournée": "Nord"}}
    response = client.post("/api/customers/", payload, format="json")
    assert response.status_code == 201, response.data
    data = response.json()
    assert all(data[key] == value for key, value in payload.items())
    assert client.post("/api/customers/", payload, format="json").status_code == 400
    Customer.objects.create(company=other, name="Autre", reference="C-2")
    assert client.post("/api/customers/", {"name": "Sans référence"}, format="json").status_code == 201
    assert client.post("/api/customers/", {"name": "Autre sans référence"}, format="json").status_code == 201
    assert client.patch(f"/api/customers/{customer.pk}/", {"reference": "C-2"}, format="json").status_code == 400
    assert client.get("/api/customers/?search=Grossistes").json()["count"] == 1
    assert client.get("/api/customers/?city=Paris&group_name=Grossistes").json()["count"] == 1
    assert AuditEvent.objects.filter(object_type="customer", object_id=str(data["id"]), actor=user).exists()


@pytest.mark.parametrize("payload", [
    {"payment_terms_days": -1}, {"payment_terms_days": 366}, {"default_discount_rate": "100.0001"}, {"default_discount_rate": 2.5},
    {"credit_limit": -1}, {"credit_limit": "-0.01"}, {"country": "FRANCE"}, {"iban": "FR1420041010050500013M02607"}, {"bic": "abc"},
    {"custom_fields": []}, {"custom_fields": {"flag": True}}, {"custom_fields": {"html": "<script>"}}, {"custom_fields": {"": "vide"}},
    {"custom_fields": {str(i): "x" for i in range(21)}}, {"custom_fields": {"long": "x" * 501}}, {"website": "https://user:password@example.com"},
])
def test_invalid_customer_parameters_are_rejected(partners, payload):
    customer, client = partners[3], partners[5]
    assert client.patch(f"/api/customers/{customer.pk}/", payload, format="json").status_code == 400


def test_products_rich_fields_and_barcode_search(partners):
    product, client = partners[4], partners[5]
    payload = {"latin_name": "Spice", "barcode": "3210001234567", "manufacturer": "Fabricant", "supplier_name": "Fournisseur", "color": "Bleu", "dimensions": "20 × 30 cm", "origin": "France", "weight": "0.123456", "notes": "Fragile", "custom_fields": {"Lot indicatif": "LOT-A"}}
    response = client.patch(f"/api/products/{product.pk}/", payload, format="json")
    assert response.status_code == 200
    assert all(response.json()[key] == value for key, value in payload.items())
    assert response.json()["unit_price"] == "12.123456"
    assert client.get("/api/products/?search=3210001234567").json()["count"] == 1
    for invalid in ("-1", 0.3, "NaN", "0.0000001", ""):
        assert client.patch(f"/api/products/{product.pk}/", {"weight": invalid}, format="json").status_code == 400
    assert client.patch(f"/api/products/{product.pk}/", {"weight": None}, format="json").status_code == 200


def test_customer_price_resolution_archiving_and_audit(partners):
    company, other, user, customer, product, client = partners
    pricing_url = f"/api/products/{product.pk}/pricing/?customer={customer.pk}"
    assert client.get(pricing_url).json() == {"product": product.pk, "customer": customer.pk, "unit_price": "12.123456", "tax_rate": "5.5000", "discount_rate": "7.1250", "source": "catalog"}
    payload = {"customer": customer.pk, "product": product.pk, "unit_price": "9.654321"}
    response = client.post("/api/customer-prices/", payload, format="json")
    assert response.status_code == 201, response.data
    price = response.json()
    assert client.get(pricing_url).json()["unit_price"] == "9.654321"
    assert client.get(pricing_url).json()["source"] == "customer"
    assert client.post("/api/customer-prices/", payload, format="json").status_code == 400
    assert client.patch(f"/api/customer-prices/{price['id']}/", {"archived": True}, format="json").status_code == 200
    assert client.get(pricing_url).json()["source"] == "catalog"
    assert client.delete(f"/api/customer-prices/{price['id']}/").status_code == 405
    assert list(AuditEvent.objects.filter(object_type="customerprice").order_by("id").values_list("action", flat=True)) == ["reference.created", "reference.updated"]
    assert client.get(f"/api/customer-prices/?customer={customer.pk}&archived=true").json()["count"] == 1


def test_customer_prices_permissions_isolation_and_transaction_rollback(partners):
    company, other, user, customer, product, client = partners
    foreign_customer = Customer.objects.create(company=other, name="Client confidentiel")
    foreign_product = Product.objects.create(company=other, name="Article confidentiel", reference="PRIVATE", unit_price="1")
    foreign_price = CustomerPrice.objects.create(company=other, customer=foreign_customer, product=foreign_product, unit_price="0.5")
    assert client.get(f"/api/customers/{foreign_customer.pk}/statement/").status_code == 404
    assert client.get(f"/api/products/{product.pk}/pricing/?customer={foreign_customer.pk}").status_code == 404
    assert client.get(f"/api/products/{foreign_product.pk}/pricing/?customer={customer.pk}").status_code == 404
    assert client.get(f"/api/customer-prices/{foreign_price.pk}/").status_code == 404
    assert client.get(f"/api/customer-prices/?customer={foreign_customer.pk}").status_code == 404
    assert client.get("/api/customer-prices/?search=confidentiel").json()["count"] == 0
    base = {"customer": customer.pk, "product": product.pk, "unit_price": "8"}
    for payload in ({**base, "customer": foreign_customer.pk}, {**base, "product": foreign_product.pk}, {**base, "company": other.pk}, {**base, "unit_price": 8.5}):
        assert client.post("/api/customer-prices/", payload, format="json").status_code == 400
    with patch("erp.partner_api.AuditEvent.objects.create", side_effect=IntegrityError("audit failed")):
        assert client.post("/api/customer-prices/", base, format="json").status_code == 400
    assert not CustomerPrice.objects.filter(company=company).exists()
    user.role = "viewer"
    user.save(update_fields=["role"])
    assert client.post("/api/customer-prices/", base, format="json").status_code == 403
    assert client.patch(f"/api/customers/{customer.pk}/", {"notes": "Non"}, format="json").status_code == 403
    assert APIClient().get(f"/api/customers/{customer.pk}/statement/").status_code == 401


def test_customer_statement_decimal_summaries_pagination_and_frozen_invoices(partners):
    company, other, user, customer, product, client = partners
    bootstrap_company(company)
    Period.objects.create(company=company, name="2026", start=date(2026, 1, 1), end=date(2026, 12, 31))
    payload = {"customer": customer.pk, "issue_date": "2026-01-03", "due_date": "2026-01-10", "document_language": "fr", "lines": [{"product": product.pk, "description": "Article facturé", "quantity": "1", "unit_price": "10.01", "tax_rate": "0"}]}
    first = save_draft(company, user, payload)
    first = validate_invoice(company, user, first.pk, "crm-validate-1")
    record_payment(company, user, first.pk, "crm-payment-1", {"amount": "3.01", "date": "2026-01-04", "reference": "Virement"})
    second = save_draft(company, user, {**payload, "issue_date": "2026-02-01", "due_date": "2026-02-15"})
    validate_invoice(company, user, second.pk, "crm-validate-2")
    save_draft(company, user, payload)  # Le brouillon ne doit entrer dans aucun total.
    before = client.get(f"/api/invoices/{first.pk}/").json()
    assert client.patch(f"/api/customers/{customer.pk}/", {"name": "Nom modifié", "default_discount_rate": "99"}, format="json").status_code == 200
    assert client.get(f"/api/invoices/{first.pk}/").json() == before
    response = client.get(f"/api/customers/{customer.pk}/statement/?page_size=1")
    assert response.status_code == 200, response.data
    data = response.json()
    assert data["count"] == 2 and len(data["results"]) == 1 and data["next"]
    assert data["summary"] == {"invoice_count": 2, "total": "20.02", "paid": "3.01", "balance": "17.01", "overdue": "17.01"}
    assert data["results"][0]["payments"][0]["amount"] == "3.01"
    filtered = client.get(f"/api/customers/{customer.pk}/statement/?start=2026-02-01&end=2026-02-28").json()
    assert filtered["count"] == 1 and filtered["summary"]["balance"] == "10.01"
    for query in ("start=invalid", "start=2026-03-01&end=2026-02-01", "page=999"):
        assert client.get(f"/api/customers/{customer.pk}/statement/?{query}").status_code in {400, 404}


def test_partner_database_constraints(partners):
    company, other, user, customer, product, client = partners
    for changes in ({"credit_limit": Decimal("-1")}, {"payment_terms_days": 366}, {"default_discount_rate": Decimal("100.01")}):
        with pytest.raises(IntegrityError), transaction.atomic():
            Customer.objects.filter(pk=customer.pk).update(**changes)
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.filter(pk=product.pk).update(weight=Decimal("-1"))
