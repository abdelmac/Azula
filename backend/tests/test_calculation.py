"""Contrôles Decimal sans base ; ne remplacent pas les tests PostgreSQL."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError

from erp.models import Company
from erp.services import DomainError, _calculate, _decimal, _fingerprint


@pytest.mark.parametrize("precision,price,tax_rate,net,tax,total", [
    (2, "100", "20", "100.00", "20.00", "120.00"),
    (2, "0.005", "20", "0.01", "0.00", "0.01"),
    (2, "0.05", "10", "0.05", "0.01", "0.06"),
    (2, "1.005", "20", "1.01", "0.20", "1.21"),
    (0, "1.5", "20", "2", "0", "2"),
    (3, "1.0005", "20", "1.001", "0.200", "1.201"),
    (4, "0.00005", "100", "0.0001", "0.0001", "0.0002"),
])
def test_exact_line_rounding(precision, price, tax_rate, net, tax, total):
    result = _calculate(SimpleNamespace(precision=precision), [{"description": "Calcul", "quantity": "1", "unit_price": price, "tax_rate": tax_rate}])[0]
    assert result["net"] == Decimal(net)
    assert result["tax"] == Decimal(tax)
    assert result["total"] == Decimal(total)
    assert all(isinstance(result[key], Decimal) for key in ("quantity", "unit_price", "tax_rate", "net", "tax", "total"))


def test_sum_of_rounded_lines_differs_from_rounding_sum():
    result = _calculate(SimpleNamespace(precision=2), [{"description": "Calcul", "quantity": "1", "unit_price": "0.005", "tax_rate": "0"}] * 2)
    assert sum((line["net"] for line in result), Decimal("0")) == Decimal("0.02")


@pytest.mark.parametrize("value", [0.1, True, None, {}, [], "NaN", "Infinity", "-Infinity", "1e2", " 1", "1 ", "", "1,00", "0.0000001", "-1", "999999999999999999999999999999999999"])
def test_invalid_decimal_inputs(value):
    with pytest.raises(DomainError, match="invalid_amount"):
        _decimal(value)


@pytest.mark.parametrize("quantity", ["0", "-1", "0.0000001", "10000000000"])
def test_invalid_quantities(quantity):
    with pytest.raises(DomainError, match="invalid_amount"):
        _calculate(SimpleNamespace(precision=2), [{"description": "Calcul", "quantity": quantity, "unit_price": "100", "tax_rate": "20"}])


@pytest.mark.parametrize("lines", [None, [], {}, [{"description": "", "quantity": "1", "unit_price": "100", "tax_rate": "20"}], [None]])
def test_invalid_line_shapes(lines):
    with pytest.raises(DomainError, match="invalid_input"):
        _calculate(SimpleNamespace(precision=2), lines)


def test_amount_bounds_prevent_database_overflow():
    with pytest.raises(DomainError, match="invalid_amount"):
        _calculate(SimpleNamespace(precision=2), [{"description": "Trop grand", "quantity": "9999999999", "unit_price": "999999999999", "tax_rate": "100"}])


def test_large_catalogue_price_can_be_used_without_losing_precision():
    result = _calculate(SimpleNamespace(precision=2), [{"description": "Prix catalogue", "quantity": "1", "unit_price": "1234567890123.45", "tax_rate": "0"}])[0]
    assert result["total"] == Decimal("1234567890123.45")


@pytest.mark.parametrize("locale,accepted", [("fr-FR", True), ("en", True), ("ar-MA", True), ("zh-Hant-TW", True), ("tr-TR", True), ("!", False), ("fr_FR", False), ("fr--FR", False), ("de-DE-DE", False)])
def test_locale_validator_accepts_documented_bcp47_subset(locale, accepted):
    field = Company._meta.get_field("locale")
    if accepted:
        field.run_validators(locale)
    else:
        with pytest.raises(ValidationError):
            field.run_validators(locale)


def test_fingerprint_stable_for_key_order_and_scoped_to_action_invoice():
    first = _fingerprint("payment", 1, {"amount": "50.00", "date": "2026-09-07"})
    assert first == _fingerprint("payment", 1, {"date": "2026-09-07", "amount": "50.00"})
    assert first == _fingerprint("payment", "1", {"amount": "50.00", "date": "2026-09-07"})
    assert first != _fingerprint("payment", 2, {"amount": "50.00", "date": "2026-09-07"})
    assert first != _fingerprint("validate", 1, {"amount": "50.00", "date": "2026-09-07"})
