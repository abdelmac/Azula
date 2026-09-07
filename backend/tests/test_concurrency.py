from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections

from erp.models import Company, Customer, Entry, Invoice, NumberSequence, Payment, User
from erp.services import DomainError, bootstrap_company, record_payment, save_draft, set_period, validate_invoice

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def concurrent_ledger():
    assert connection.vendor == "postgresql"
    company = Company.objects.create(name="Concurrence PostgreSQL")
    actor = User.objects.create_user(username="concurrent-admin", company=company, role="admin")
    customer = Customer.objects.create(company=company, name="Client")
    bootstrap_company(company)
    set_period(company, actor, {"name": "2026", "start": "2026-01-01", "end": "2026-12-31"})
    invoices = [save_draft(company, actor, {"customer": customer.pk, "issue_date": "2026-09-07", "due_date": "2026-10-07", "lines": [{"description": "Concurrence", "quantity": "1", "unit_price": "100", "tax_rate": "20"}]}) for _ in range(2)]
    return company, actor, invoices


def race(company, actor, jobs):
    barrier = Barrier(len(jobs))

    def worker(job):
        close_old_connections()
        try:
            local_company = Company.objects.get(pk=company.pk)
            local_actor = User.objects.get(pk=actor.pk)
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '10s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                backend_pid = cursor.fetchone()[0]
            barrier.wait(timeout=10)
            try:
                invoice = job(local_company, local_actor)
                return backend_pid, "ok", invoice.pk
            except DomainError as error:
                return backend_pid, error.code, None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = [executor.submit(worker, job) for job in jobs]
        results = [future.result(timeout=25) for future in futures]
    assert len({result[0] for result in results}) == len(jobs), "Connexions PostgreSQL indépendantes requises"
    return [result[1] for result in results]


def test_concurrent_validation_same_key_exactly_once(concurrent_ledger):
    company, actor, invoices = concurrent_ledger
    invoice = invoices[0]
    jobs = [lambda c, a: validate_invoice(c, a, invoice.pk, "same-key")] * 2
    assert race(company, actor, jobs) == ["ok", "ok"]
    assert Entry.objects.filter(invoice=invoice).count() == 1
    assert NumberSequence.objects.get(company=company).next_value == 2


def test_concurrent_validation_different_keys_cannot_duplicate(concurrent_ledger):
    company, actor, invoices = concurrent_ledger
    invoice = invoices[0]
    results = race(company, actor, [lambda c, a: validate_invoice(c, a, invoice.pk, "key-a"), lambda c, a: validate_invoice(c, a, invoice.pk, "key-b")])
    assert sorted(results) == ["already_validated", "ok"]
    assert Entry.objects.filter(invoice=invoice).count() == 1


def test_concurrent_invoices_receive_distinct_sequence_numbers(concurrent_ledger):
    company, actor, invoices = concurrent_ledger
    assert race(company, actor, [lambda c, a: validate_invoice(c, a, invoices[0].pk, "invoice-a"), lambda c, a: validate_invoice(c, a, invoices[1].pk, "invoice-b")]) == ["ok", "ok"]
    numbers = set(Invoice.objects.filter(company=company).values_list("number", flat=True))
    assert numbers == {"INV-2026-000001", "INV-2026-000002"}


def test_concurrent_double_payment_cannot_overpay(concurrent_ledger):
    company, actor, invoices = concurrent_ledger
    invoice = validate_invoice(company, actor, invoices[0].pk, "validate")
    payload = {"amount": "120", "date": "2026-09-07"}
    results = race(company, actor, [lambda c, a: record_payment(c, a, invoice.pk, "pay-a", payload), lambda c, a: record_payment(c, a, invoice.pk, "pay-b", payload)])
    assert sorted(results) == ["ok", "overpayment"]
    assert Payment.objects.filter(invoice=invoice).count() == 1
    assert Invoice.objects.get(pk=invoice.pk).balance == Decimal("0")


def test_concurrent_payment_retry_same_key_exactly_once(concurrent_ledger):
    company, actor, invoices = concurrent_ledger
    invoice = validate_invoice(company, actor, invoices[0].pk, "validate")
    payload = {"amount": "50", "date": "2026-09-07"}
    assert race(company, actor, [lambda c, a: record_payment(c, a, invoice.pk, "same-payment", payload)] * 2) == ["ok", "ok"]
    assert Payment.objects.filter(invoice=invoice).count() == 1
    assert Invoice.objects.get(pk=invoice.pk).balance == Decimal("70")


def test_concurrent_key_reuse_with_different_content_rejected(concurrent_ledger):
    company, actor, invoices = concurrent_ledger
    invoice = validate_invoice(company, actor, invoices[0].pk, "validate")
    results = race(company, actor, [lambda c, a: record_payment(c, a, invoice.pk, "conflicting-payment", {"amount": "30", "date": "2026-09-07"}), lambda c, a: record_payment(c, a, invoice.pk, "conflicting-payment", {"amount": "40", "date": "2026-09-07"})])
    assert sorted(results) == ["idempotency_conflict", "ok"]
    assert Payment.objects.filter(invoice=invoice).count() == 1
