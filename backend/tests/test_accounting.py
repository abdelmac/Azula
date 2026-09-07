from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from erp.models import (
    Account,
    AuditEvent,
    Company,
    Customer,
    Entry,
    EntryLine,
    IdempotencyRecord,
    Invoice,
    InvoiceLine,
    NumberSequence,
    Payment,
    Product,
    User,
)
from erp.services import (
    DomainError,
    bootstrap_company,
    configure_company,
    record_payment,
    save_draft,
    set_period,
    validate_invoice,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def ledger():
    assert connection.vendor == "postgresql", "Les invariants sont testés uniquement sur PostgreSQL."
    company = Company.objects.create(name="Société témoin", address="Adresse initiale")
    actor = User.objects.create_user(username="comptable", company=company, role="admin")
    customer = Customer.objects.create(company=company, name="Client initial", tax_id="DEMO-123")
    bootstrap_company(company)
    period = set_period(company, actor, {"name": "2026", "start": "2026-01-01", "end": "2026-12-31"})
    return company, actor, customer, period


def draft(ledger, *, lines=None):
    company, actor, customer, _ = ledger
    return save_draft(company, actor, {
        "customer": customer.pk, "issue_date": "2026-09-07", "due_date": "2026-10-07",
        "document_language": "fr", "lines": lines or [{"description": "Prestation", "quantity": "1", "unit_price": "100.00", "tax_rate": "20"}],
    })


def validated(ledger):
    invoice = draft(ledger)
    return validate_invoice(ledger[0], ledger[1], invoice.pk, "validation-1")


def test_vertical_100_20_payments_50_70_and_retry(ledger):
    company, actor, _, period = ledger
    invoice = validated(ledger)
    assert (invoice.net, invoice.tax, invoice.total) == (Decimal("100.00"), Decimal("20.00"), Decimal("120.00"))
    sales = Entry.objects.get(invoice=invoice, kind="invoice")
    postings = {line.account.kind: (line.debit, line.credit) for line in sales.lines.select_related("account")}
    assert postings == {"receivable": (Decimal("120"), Decimal("0")), "revenue": (Decimal("0"), Decimal("100")), "tax": (Decimal("0"), Decimal("20"))}
    assert sales.total_debit == sales.total_credit == Decimal("120")
    invoice = record_payment(company, actor, invoice.pk, "payment-50", {"amount": "50.00", "date": "2026-09-07", "reference": "VIR-1"})
    assert invoice.paid == Decimal("50") and invoice.balance == Decimal("70")
    bank = Entry.objects.get(payment__invoice=invoice)
    postings = {line.account.kind: (line.debit, line.credit) for line in bank.lines.select_related("account")}
    assert postings == {"bank": (Decimal("50"), Decimal("0")), "receivable": (Decimal("0"), Decimal("50"))}
    payload = {"amount": "70.00", "date": "2026-09-07", "reference": "VIR-2"}
    invoice = record_payment(company, actor, invoice.pk, "payment-70", payload)
    invoice = record_payment(company, actor, invoice.pk, "payment-70", payload)
    assert invoice.balance == 0 and invoice.payments.count() == 2
    assert Entry.objects.filter(period=period).count() == 3
    assert sum((entry.total_debit for entry in Entry.objects.all()), Decimal("0")) == Decimal("240")
    assert IdempotencyRecord.objects.count() == 3
    assert AuditEvent.objects.filter(action="invoice.validated").count() == 1
    assert AuditEvent.objects.filter(action="payment.recorded").count() == 2


def test_rounding_half_up_each_line_then_sum(ledger):
    invoice = draft(ledger, lines=[{"description": "Fraction", "quantity": "1", "unit_price": "0.005", "tax_rate": "20"}] * 2)
    assert invoice.net == Decimal("0.02")
    assert invoice.tax == Decimal("0.00")
    invoice = validate_invoice(ledger[0], ledger[1], invoice.pk, "fraction")
    assert invoice.snapshot["rounding"] == {"mode": "ROUND_HALF_UP", "scope": "line", "tax_base": "rounded_net"}
    assert [line["net"] for line in invoice.snapshot["lines"]] == ["0.01", "0.01"]


def test_half_up_tax_and_no_float(ledger):
    invoice = draft(ledger, lines=[{"description": "Taxe fractionnaire", "quantity": "1", "unit_price": "0.05", "tax_rate": "10"}])
    assert invoice.tax == Decimal("0.01")
    with pytest.raises(DomainError, match="invalid_amount"):
        draft(ledger, lines=[{"description": "Flottant", "quantity": "1", "unit_price": 0.1, "tax_rate": "0"}])


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "1e2", "0.001", "120.01", "999999999999999999999999999999999999"])
def test_invalid_payments_leave_no_trace(ledger, value):
    invoice = validated(ledger)
    with pytest.raises(DomainError) as failure:
        record_payment(ledger[0], ledger[1], invoice.pk, "invalid", {"amount": value, "date": "2026-09-07", "reference": ""})
    assert failure.value.code in {"invalid_amount", "overpayment"}
    assert Payment.objects.count() == 0
    assert Entry.objects.count() == 1


@pytest.mark.parametrize("field,value", [("quantity", "0"), ("quantity", "-1"), ("unit_price", "-1"), ("tax_rate", "100.0001"), ("tax_rate", "-0.01"), ("quantity", "0.0000001")])
def test_invalid_lines(ledger, field, value):
    line = {"description": "Ligne", "quantity": "1", "unit_price": "100", "tax_rate": "20"}
    line[field] = value
    with pytest.raises(DomainError, match="invalid_amount"):
        draft(ledger, lines=[line])
    assert Invoice.objects.count() == 0


def test_keys_required_unique_and_content_checked(ledger):
    company, actor, _, _ = ledger
    invoice = draft(ledger)
    with pytest.raises(DomainError, match="idempotency_required"):
        validate_invoice(company, actor, invoice.pk, "")
    invoice = validate_invoice(company, actor, invoice.pk, "same")
    assert validate_invoice(company, actor, invoice.pk, "same").number == invoice.number
    with pytest.raises(DomainError, match="idempotency_conflict"):
        validate_invoice(company, actor, invoice.pk, "same", {"changed": True})
    with pytest.raises(DomainError, match="already_validated"):
        validate_invoice(company, actor, invoice.pk, "another")
    with pytest.raises(DomainError, match="idempotency_conflict"):
        record_payment(company, actor, invoice.pk, "same", {"amount": "50", "date": "2026-09-07"})
    record_payment(company, actor, invoice.pk, "pay", {"amount": "50", "date": "2026-09-07"})
    with pytest.raises(DomainError, match="idempotency_conflict"):
        record_payment(company, actor, invoice.pk, "pay", {"amount": "40", "date": "2026-09-07"})
    # Chaînes décimales équivalentes désignent le même règlement.
    record_payment(company, actor, invoice.pk, "pay", {"amount": "50.00", "date": "2026-09-07"})
    assert Payment.objects.count() == 1


def test_closed_period_blocks_validation_payment_and_direct_entry(ledger):
    company, actor, _, period = ledger
    invoice = validated(ledger)
    pending = draft(ledger)
    set_period(company, actor, {"closed": True}, period.pk)
    with pytest.raises(DomainError, match="period_closed"):
        validate_invoice(company, actor, pending.pk, "closed-validate")
    with pytest.raises(DomainError, match="period_closed"):
        record_payment(company, actor, invoice.pk, "closed-pay", {"amount": "50", "date": "2026-09-07"})
    pending.refresh_from_db()
    assert pending.status == "draft" and pending.number == ""
    assert NumberSequence.objects.get(company=company).next_value == 2
    assert Payment.objects.count() == 0
    existing = Entry.objects.get(invoice=invoice)
    with pytest.raises(IntegrityError, match="period_closed_or_invalid"), transaction.atomic():
        Entry.objects.create(company=company, invoice=invoice, period=period, journal=existing.journal, date=invoice.issue_date, reference="CLOSED", kind="invoice")


def test_period_missing_and_overlaps(ledger):
    company, actor, customer, _ = ledger
    invoice = save_draft(company, actor, {"customer": customer.pk, "issue_date": "2027-01-01", "due_date": "2027-02-01", "lines": [{"description": "Future", "quantity": "1", "unit_price": "100", "tax_rate": "0"}]})
    with pytest.raises(DomainError, match="period_missing"):
        validate_invoice(company, actor, invoice.pk, "missing")
    with pytest.raises(DomainError, match="invalid_input"):
        set_period(company, actor, {"name": "Chevauchement", "start": "2026-12-31", "end": "2027-01-01"})


def test_snapshot_survives_reference_changes_and_configuration_locked(ledger):
    company, actor, customer, _ = ledger
    product = Product.objects.create(company=company, reference="P-1", name="Prestation", unit_price=Decimal("100"), tax_rate=Decimal("20"))
    invoice = draft(ledger, lines=[{"product": product.pk, "description": "Nom figé", "quantity": "1", "unit_price": "100", "tax_rate": "20"}])
    invoice = validate_invoice(company, actor, invoice.pk, "snapshot")
    snapshot = invoice.snapshot
    Customer.objects.filter(pk=customer.pk).update(name="Nouveau client", address="Autre adresse")
    Product.objects.filter(pk=product.pk).update(name="Autre prestation", unit_price=Decimal("200"), reference="P-2")
    configure_company(company, actor, {"name": "Nouvelle société"})
    invoice.refresh_from_db()
    assert invoice.snapshot == snapshot
    assert snapshot["company"]["name"] == "Société témoin"
    assert snapshot["customer"]["name"] == "Client initial"
    assert snapshot["lines"][0]["product_reference"] == "P-1"
    for data in ({"precision": 3}, {"currency": "USD"}):
        with pytest.raises(DomainError, match="configuration_locked"):
            configure_company(company, actor, data)


def test_draft_recalculated_and_precision_frozen(ledger):
    company, actor, _, _ = ledger
    invoice = draft(ledger, lines=[{"description": "Arrondi entier", "quantity": "1", "unit_price": "1.5", "tax_rate": "0"}])
    configure_company(company, actor, {"precision": 0, "currency": "JPY"})
    invoice = validate_invoice(company, actor, invoice.pk, "precision")
    assert invoice.precision == 0 and invoice.total == Decimal("2") and invoice.currency == "JPY"
    assert invoice.snapshot["total"] == "2"
    with pytest.raises(DomainError, match="invalid_amount"):
        record_payment(company, actor, invoice.pk, "fraction", {"amount": "0.5", "date": "2026-09-07"})


def test_immutability_in_model_services_and_bulk_database_mutations(ledger):
    company, actor, _, _ = ledger
    invoice = validated(ledger)
    with pytest.raises(ValidationError, match="immutable"):
        invoice.save()
    with pytest.raises(ValidationError, match="immutable"):
        invoice.delete()
    with pytest.raises(DomainError, match="immutable"):
        save_draft(company, actor, {"due_date": "2026-12-01"}, invoice.pk)
    record_payment(company, actor, invoice.pk, "immutable-pay", {"amount": "50", "date": "2026-09-07"})
    operations = [
        lambda: Invoice.objects.filter(pk=invoice.pk).update(due_date=date(2026, 12, 1)),
        lambda: InvoiceLine.objects.filter(invoice=invoice).update(description="Altération"),
        lambda: InvoiceLine.objects.filter(invoice=invoice).delete(),
        lambda: Entry.objects.all().update(reference="Altération"),
        lambda: EntryLine.objects.all().update(debit=Decimal("1")),
        lambda: Payment.objects.all().update(reference="Altération"),
        lambda: AuditEvent.objects.all().update(action="Altération"),
        lambda: Company.objects.filter(pk=company.pk).update(precision=3),
    ]
    for operation in operations:
        with pytest.raises(IntegrityError), transaction.atomic():
            operation()


def test_database_rejects_extra_entry_lines(ledger):
    invoice = validated(ledger)
    entry = Entry.objects.get(invoice=invoice)
    account = Account.objects.get(company=ledger[0], kind="bank")
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        EntryLine.objects.create(company=ledger[0], entry=entry, account=account, debit=Decimal("1"), credit=Decimal("0"))


def test_database_rejects_unbalanced_and_orphan_payment(ledger):
    invoice = validated(ledger)
    company = ledger[0]
    with pytest.raises(IntegrityError, match="payment_entry_missing"), transaction.atomic():
        Payment.objects.create(company=company, invoice=invoice, amount=Decimal("1"), date=date(2026, 9, 7))
    with pytest.raises(IntegrityError, match="unbalanced_entry"), transaction.atomic():
        payment = Payment.objects.create(company=company, invoice=invoice, amount=Decimal("10"), date=date(2026, 9, 7))
        previous = Entry.objects.get(invoice=invoice)
        entry = Entry.objects.create(company=company, invoice=invoice, payment=payment, period=ledger[3], journal=previous.journal, kind="payment", date=payment.date, reference="UNBALANCED")
        EntryLine.objects.create(company=company, entry=entry, account=Account.objects.get(company=company, kind="bank"), debit=Decimal("10"), credit=Decimal("0"))
    assert Payment.objects.count() == 0


def test_failure_rolls_back_invoice_number_entry_audit_key(ledger, monkeypatch):
    invoice = draft(ledger)

    def fail(*args, **kwargs):
        raise RuntimeError("Simulation d'une panne avant commit")

    monkeypatch.setattr("erp.services._audit", fail)
    with pytest.raises(RuntimeError):
        validate_invoice(ledger[0], ledger[1], invoice.pk, "rollback")
    invoice.refresh_from_db()
    assert invoice.status == "draft" and invoice.number == "" and invoice.snapshot == {}
    assert Entry.objects.count() == IdempotencyRecord.objects.count() == NumberSequence.objects.count() == 0


def test_nested_transaction_supports_entry_creation(ledger):
    with transaction.atomic():
        invoice = validated(ledger)
        record_payment(ledger[0], ledger[1], invoice.pk, "nested", {"amount": "50", "date": "2026-09-07"})
    assert Entry.objects.count() == 2


def test_roles_and_cross_company_service_references(ledger):
    company, actor, _, _ = ledger
    other = Company.objects.create(name="Autre société")
    foreign_customer = Customer.objects.create(company=other, name="Autre client")
    foreign_product = Product.objects.create(company=other, name="Autre", reference="OTHER", unit_price=Decimal("10"), tax_rate=Decimal("0"))
    with pytest.raises(DomainError, match="not_found"):
        save_draft(company, actor, {"customer": foreign_customer.pk})
    with pytest.raises(DomainError, match="not_found"):
        draft(ledger, lines=[{"product": foreign_product.pk, "description": "Autre", "quantity": "1", "unit_price": "10", "tax_rate": "0"}])
    invoice = draft(ledger)
    actor.role = "sales"
    with pytest.raises(DomainError, match="permission_denied"):
        validate_invoice(company, actor, invoice.pk, "unauthorized")
    actor.role = "viewer"
    with pytest.raises(DomainError, match="permission_denied"):
        draft(ledger)
    actor.role = "admin"
    with pytest.raises(DomainError, match="permission_denied"):
        validate_invoice(other, actor, invoice.pk, "other")


def test_archived_references_block_validation(ledger):
    invoice = draft(ledger)
    Customer.objects.filter(pk=ledger[2].pk).update(archived=True)
    with pytest.raises(DomainError, match="archived_reference"):
        validate_invoice(ledger[0], ledger[1], invoice.pk, "archived")
