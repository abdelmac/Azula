"""Contrôles exécutables sans base : barrière anonyme, CSRF et formats d'entrée.

Ces contrôles ne remplacent pas test_api.py, qui exige PostgreSQL.
"""

import pytest
from rest_framework.test import APIClient

from erp.serializers import DraftSerializer, PaymentInputSerializer


def test_anonymous_login_without_csrf_is_rejected_before_authentication():
    client = APIClient(enforce_csrf_checks=True)
    response = client.post("/api/auth/login/", {"username": "anonymous", "password": "never-checked"}, format="json")
    assert response.status_code == 403
    assert response.json() == {"code": "csrf_failed", "detail": "csrf_failed"}


def test_anonymous_csrf_endpoint_and_invalid_login_contract():
    client = APIClient(enforce_csrf_checks=True)
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 200
    token = response.json()["csrfToken"]
    assert len(token) == 64
    assert "no-store" in response["Cache-Control"]
    response = client.post("/api/auth/login/", {"username": "anonymous", "password": "never-checked", "role": "admin"}, format="json", HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_input"


@pytest.mark.parametrize("endpoint", ["auth/me/", "company/", "customers/", "products/", "invoices/", "entries/", "trial-balance/?period=1", "periods/", "users/", "audit/"])
def test_anonymous_business_access_is_refused(endpoint):
    response = APIClient().get("/api/" + endpoint)
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


@pytest.mark.parametrize("amount", [50.0, 50, "1e2", "NaN", "Infinity", " 50.00 ", "50,00", "-1", "0"])
def test_payment_requires_explicit_positive_decimal_string(amount):
    serializer = PaymentInputSerializer(data={"amount": amount, "date": "2026-09-07"})
    assert not serializer.is_valid()


def test_payment_precision_is_preserved_without_binary_float():
    serializer = PaymentInputSerializer(data={"amount": "50.005", "date": "2026-09-07"})
    assert serializer.is_valid(), serializer.errors
    assert str(serializer.validated_data["amount"]) == "50.005000"


@pytest.mark.parametrize("field,value", [("company", 2), ("status", "validated"), ("number", "FAKE"), ("total", "0.01"), ("snapshot", {})])
def test_invoice_internal_fields_cannot_enter_financial_service(field, value):
    serializer = DraftSerializer(data={"customer": 1, "issue_date": "2026-09-07", "due_date": "2026-09-07", "document_language": "fr", "lines": [{"description": "Service", "quantity": "1", "unit_price": "100.00", "tax_rate": "20"}], field: value})
    assert not serializer.is_valid()
    assert field in serializer.errors
