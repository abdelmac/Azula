"""Catalogue : paramètres, isolation, décimales et conservation des factures (PostgreSQL)."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APIClient

from erp.models import (
    AuditEvent,
    Company,
    Customer,
    Period,
    Product,
    ProductCategory,
    Unit,
    User,
    Warehouse,
)
from erp.services import bootstrap_company, save_draft, validate_invoice

pytestmark = pytest.mark.django_db(transaction=True)

REFERENCES = [("product-categories", ProductCategory), ("warehouses", Warehouse), ("units", Unit)]


@pytest.fixture
def catalog():
    company = Company.objects.create(name="Catalogue", currency="EUR", precision=2)
    other = Company.objects.create(name="Catalogue privé")
    users = {role: User.objects.create_user(username=f"catalog-{role}", company=company, role=role) for role in ("admin", "accountant", "sales", "viewer")}
    category = ProductCategory.objects.create(company=company, code="EP", name="Épices")
    unit = Unit.objects.create(company=company, code="PCS", name="Pièce")
    warehouse = Warehouse.objects.create(company=company, code="PAR", name="Paris")
    product = Product.objects.create(company=company, reference="SP-001", name="Cumin", unit_price="3.250001", purchase_price="1.123456", tax_rate="5.5", category=category, unit=unit, specifications="Conditionnement 12 × 25 g")
    product.warehouses.add(warehouse)
    client = APIClient()
    client.force_authenticate(users["admin"])
    return {"company": company, "other": other, "users": users, "category": category, "unit": unit, "warehouse": warehouse, "product": product, "client": client}


def product_input(**changes):
    return {"reference": "NEW", "name": "Article", "unit_price": "9.123456", "tax_rate": "20", **changes}


@pytest.mark.parametrize("endpoint,model", REFERENCES)
@pytest.mark.parametrize("role,allowed", [("admin", True), ("accountant", True), ("sales", True), ("viewer", False)])
def test_catalog_reference_permissions(catalog, endpoint, model, role, allowed):
    client = catalog["client"]
    client.force_authenticate(catalog["users"][role])
    response = client.post(f"/api/{endpoint}/", {"code": "NEW", "name": "Nouveau"}, format="json")
    assert response.status_code == (201 if allowed else 403)
    obj = model.objects.create(company=catalog["company"], code="EDIT", name="Existant")
    url = f"/api/{endpoint}/{obj.pk}/"
    assert client.get(f"/api/{endpoint}/").status_code == 200
    assert client.get(url).status_code == 200
    assert client.patch(url, {"archived": True}, format="json").status_code == (200 if allowed else 403)
    assert client.delete(url).status_code == 405
    assert client.put(url, {"code": "REPLACE", "name": "Remplacement"}, format="json").status_code == 405


@pytest.mark.parametrize("endpoint,model", REFERENCES)
def test_catalog_references_are_private_unique_and_audited(catalog, endpoint, model):
    client = catalog["client"]
    assert APIClient().get(f"/api/{endpoint}/").status_code == 401
    foreign = model.objects.create(company=catalog["other"], code="PRIVATE", name="Référence secrète")
    url = f"/api/{endpoint}/{foreign.pk}/"
    assert client.get(url).status_code == 404
    assert client.patch(url, {"name": "Attaque"}, format="json").status_code == 404
    assert client.get(f"/api/{endpoint}/?search=secrète").json()["count"] == 0
    response = client.post(f"/api/{endpoint}/", {"code": "PRIVATE", "name": "Autre société autorisée"}, format="json")
    assert response.status_code == 201
    obj_id = response.json()["id"]
    assert response.json() == {"id": obj_id, "code": "PRIVATE", "name": "Autre société autorisée", "archived": False}
    assert client.post(f"/api/{endpoint}/", {"code": "PRIVATE", "name": "Doublon"}, format="json").status_code == 400
    assert client.post(f"/api/{endpoint}/", {"code": "FORGED", "name": "Usurpation", "company": catalog["other"].pk}, format="json").status_code == 400
    url = f"/api/{endpoint}/{obj_id}/"
    assert client.patch(url, {"name": "Renommée", "archived": True}, format="json").status_code == 200
    assert client.get(f"/api/{endpoint}/?archived=true").json()["results"][0]["id"] == obj_id
    assert client.get(f"/api/{endpoint}/?archived=false&search=PRIVATE").json()["count"] == 0
    assert client.get(f"/api/{endpoint}/?archived=invalid").status_code == 400
    events = list(AuditEvent.objects.filter(company=catalog["company"], object_type=model.__name__.lower(), object_id=str(obj_id)).order_by("id"))
    assert [event.action for event in events] == ["reference.created", "reference.updated"]
    assert events[1].metadata == {"fields": ["archived", "name"]}
    assert all(event.actor_id == catalog["users"]["admin"].pk for event in events)
    assert not AuditEvent.objects.filter(company=catalog["other"]).exists()


def test_product_catalog_exact_values_and_nullable_defaults(catalog):
    client = catalog["client"]
    response = client.post("/api/products/", product_input(), format="json")
    assert response.status_code == 201
    default = response.json()
    assert default["purchase_price"] is None
    assert default["category"] is None and default["category_name"] is None
    assert default["unit"] is None and default["unit_name"] is None
    assert default["warehouses"] == []
    assert default["specifications"] == default["image_url"] == ""
    data = product_input(reference="FULL", purchase_price="1234567890123456.123456", category=catalog["category"].pk, unit=catalog["unit"].pk, warehouses=[catalog["warehouse"].pk], specifications="Sans sel ajouté", image_url="https://images.example.invalid/cumin.png")
    response = client.post("/api/products/", data, format="json")
    assert response.status_code == 201, response.data
    result = response.json()
    assert result["purchase_price"] == "1234567890123456.123456"
    assert result["unit_price"] == "9.123456"
    assert result["category_name"] == "Épices" and result["unit_name"] == "Pièce"
    assert result["warehouses"] == [catalog["warehouse"].pk]
    assert result["specifications"] == data["specifications"] and result["image_url"] == data["image_url"]
    assert Product.objects.get(pk=result["id"]).purchase_price == Decimal("1234567890123456.123456")
    assert client.patch(f"/api/products/{result['id']}/", {"purchase_price": None}, format="json").json()["purchase_price"] is None


@pytest.mark.parametrize("price", [1.2, 1, "-0.01", "1e2", "NaN", "Infinity", "1.1234567", "12345678901234567", "", " ", "\t\r\n", "\u00a0", " 1.00 "])
def test_purchase_price_rejects_floats_and_invalid_precision(catalog, price):
    response = catalog["client"].patch(f"/api/products/{catalog['product'].pk}/", {"purchase_price": price}, format="json")
    assert response.status_code == 400
    catalog["product"].refresh_from_db()
    assert catalog["product"].purchase_price == Decimal("1.123456")


@pytest.mark.parametrize("url", ["http://images.example.invalid/a.png", "javascript:alert(1)", "data:image/png;base64,AAAA", "https://user:password@images.example.invalid/a.png", "https://user@images.example.invalid/a.png", "/local.png"])
def test_product_images_require_https_without_credentials(catalog, url):
    assert catalog["client"].patch(f"/api/products/{catalog['product'].pk}/", {"image_url": url}, format="json").status_code == 400


def test_product_catalog_text_limits_and_readonly_names(catalog):
    url = f"/api/products/{catalog['product'].pk}/"
    for payload in ({"specifications": "x" * 4001}, {"image_url": "https://example.invalid/" + "x" * 1000}, {"category_name": "Injected"}, {"unit_name": "Injected"}):
        assert catalog["client"].patch(url, payload, format="json").status_code == 400
    assert catalog["client"].patch(url, {"specifications": "x" * 4000, "image_url": ""}, format="json").status_code == 200


@pytest.mark.parametrize("field,model", [("category", ProductCategory), ("unit", Unit), ("warehouses", Warehouse)])
def test_cross_company_product_relations_are_rejected(catalog, field, model):
    foreign = model.objects.create(company=catalog["other"], code="SECRET", name="Privée")
    value = [foreign.pk] if field == "warehouses" else foreign.pk
    client = catalog["client"]
    assert client.post("/api/products/", product_input(**{field: value}), format="json").status_code == 400
    assert client.patch(f"/api/products/{catalog['product'].pk}/", {field: value}, format="json").status_code == 400
    assert Product.objects.filter(company=catalog["company"]).count() == 1


@pytest.mark.parametrize("field,model,key,endpoint", [("category", ProductCategory, "category", "product-categories"), ("unit", Unit, "unit", "units"), ("warehouses", Warehouse, "warehouse", "warehouses")])
def test_archived_relations_can_be_retained_but_not_assigned(catalog, field, model, key, endpoint):
    client = catalog["client"]
    obj = catalog[key]
    value = [obj.pk] if field == "warehouses" else obj.pk
    assert client.patch(f"/api/{endpoint}/{obj.pk}/", {"archived": True}, format="json").status_code == 200
    assert client.post("/api/products/", product_input(**{field: value}), format="json").status_code == 400
    url = f"/api/products/{catalog['product'].pk}/"
    assert client.patch(url, {field: value, "name": "Lien historique conservé"}, format="json").status_code == 200
    another = model.objects.create(company=catalog["company"], code="OLD", name="Autre archive", archived=True)
    replacement = [obj.pk, another.pk] if field == "warehouses" else another.pk
    assert client.patch(url, {field: replacement}, format="json").status_code == 400
    cleared = [] if field == "warehouses" else None
    assert client.patch(url, {field: cleared}, format="json").status_code == 200
    assert client.patch(url, {field: value}, format="json").status_code == 400


def test_product_filters_search_and_ordering(catalog):
    client = catalog["client"]
    product = catalog["product"]
    other = Product.objects.create(company=catalog["company"], reference="SP-002", name="Cumin", unit_price="11", purchase_price="8.000001", tax_rate="0", archived=True)
    unknown = Product.objects.create(company=catalog["company"], reference="UNKNOWN", name="Sans tarif achat", unit_price="0", tax_rate="0")
    for params in ({"product": product.pk}, {"category": catalog["category"].pk}, {"warehouse": catalog["warehouse"].pk}, {"unit": catalog["unit"].pk}, {"specifications": "25 G"}, {"search": "EP"}, {"search": "conditionnement"}, {"search": "SP-001"}):
        response = client.get("/api/products/", params)
        assert response.status_code == 200
        assert [row["id"] for row in response.json()["results"]] == [product.pk]
    assert [row["id"] for row in client.get("/api/products/?archived=true").json()["results"]] == [other.pk]
    assert client.get("/api/products/", {"category": catalog["category"].pk, "archived": "true"}).json()["count"] == 0
    for ordering, expected in [("purchase_price", [product.pk, other.pk, unknown.pk]), ("unit_price", [unknown.pk, product.pk, other.pk]), ("name", [product.pk, other.pk, unknown.pk]), ("-reference", [unknown.pk, other.pk, product.pk])]:
        rows = client.get("/api/products/", {"ordering": ordering}).json()["results"]
        assert [row["id"] for row in rows] == expected


@pytest.mark.parametrize("field,model", [("product", Product), ("category", ProductCategory), ("warehouse", Warehouse), ("unit", Unit)])
def test_product_filters_hide_foreign_objects_and_validate_ids(catalog, field, model):
    data = {"reference": "SECRET", "name": "Privé", "unit_price": "2"} if model is Product else {"code": "SECRET", "name": "Privé"}
    foreign = model.objects.create(company=catalog["other"], **data)
    client = catalog["client"]
    assert client.get("/api/products/", {field: foreign.pk}).status_code == 404
    assert client.get("/api/products/", {field: 999999999}).status_code == 404
    for value in ("", "1.2", "-1", "1" * 19, "١"):
        assert client.get("/api/products/", {field: value}).status_code == 400
    assert client.get("/api/products/", {"specifications": "x" * 129}).status_code == 400
    assert client.get("/api/products/", {"search": "Privé"}).json()["count"] == 0


def test_product_audit_failure_rolls_back_fields_and_relations(catalog):
    other = Warehouse.objects.create(company=catalog["company"], code="NEW", name="Nouveau dépôt")
    with patch("erp.api.AuditEvent.objects.create", side_effect=IntegrityError("audit unavailable")):
        response = catalog["client"].patch(f"/api/products/{catalog['product'].pk}/", {"purchase_price": "2.50", "warehouses": [other.pk]}, format="json")
    assert response.status_code == 400
    catalog["product"].refresh_from_db()
    assert catalog["product"].purchase_price == Decimal("1.123456")
    assert list(catalog["product"].warehouses.all()) == [catalog["warehouse"]]
    assert not AuditEvent.objects.exists()


def test_purchase_price_database_constraint(catalog):
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.filter(pk=catalog["product"].pk).update(purchase_price=Decimal("-0.000001"))


def test_product_changes_do_not_change_validated_invoice_snapshot(catalog):
    company, user, product = catalog["company"], catalog["users"]["admin"], catalog["product"]
    bootstrap_company(company)
    Period.objects.create(company=company, name="2026", start=date(2026, 1, 1), end=date(2026, 12, 31))
    customer = Customer.objects.create(company=company, name="Client historique")
    invoice = save_draft(company, user, {"customer": customer.pk, "issue_date": "2026-09-08", "due_date": "2026-10-08", "document_language": "fr", "lines": [{"product": product.pk, "description": "Cumin facturé", "quantity": "2", "unit_price": "3.250001", "tax_rate": "5.5"}]})
    invoice = validate_invoice(company, user, invoice.pk, "catalog-snapshot")
    snapshot = invoice.snapshot
    before = catalog["client"].get(f"/api/invoices/{invoice.pk}/").json()
    assert catalog["client"].patch(f"/api/products/{product.pk}/", {"reference": "CHANGED", "name": "Nouveau nom", "unit_price": "999", "purchase_price": "500", "specifications": "Nouveau conditionnement", "unit": None, "category": None, "warehouses": [], "archived": True}, format="json").status_code == 200
    invoice.refresh_from_db()
    assert invoice.snapshot == snapshot
    assert catalog["client"].get(f"/api/invoices/{invoice.pk}/").json() == before


def test_catalog_migration_preserves_existing_product_and_invoice():
    """Ancien schéma vers nouveau schéma, uniquement dans la base pytest."""
    old = [("erp", "0004_alter_company_locale")]
    new = [("erp", "0005_catalog_parameters")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    executor.migrate(old)
    try:
        apps = executor.loader.project_state(old).apps
        company = apps.get_model("erp", "Company").objects.create(name="Avant migration")
        customer = apps.get_model("erp", "Customer").objects.create(company_id=company.pk, name="Client conservé")
        product = apps.get_model("erp", "Product").objects.create(company_id=company.pk, reference="EXISTING", name="Article conservé", unit_price=Decimal("3.141592"), tax_rate=Decimal("5.5"))
        invoice_model = apps.get_model("erp", "Invoice")
        invoice = invoice_model.objects.create(company_id=company.pk, customer_id=customer.pk, issue_date=date(2026, 9, 8), due_date=date(2026, 10, 8), net=Decimal("3.14"), tax=Decimal("0.17"), total=Decimal("3.31"))
        before = invoice_model.objects.values().get(pk=invoice.pk)
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        current_apps = executor.loader.project_state(new).apps
        current = current_apps.get_model("erp", "Product").objects.get(pk=product.pk)
        assert current.reference == "EXISTING" and current.unit_price == Decimal("3.141592")
        assert current.category_id is current.unit_id is current.purchase_price is None
        assert current.specifications == current.image_url == ""
        assert not current.warehouses.exists()
        assert current_apps.get_model("erp", "Invoice").objects.values().get(pk=invoice.pk) == before
    finally:
        MigrationExecutor(connection).migrate(latest)
