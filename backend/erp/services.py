"""Opérations métier : décimales exactes et sérialisation par société.

Le verrou de société simplifie volontairement la première version : les mutations
financières d'une société sont sérialisées, y compris les fermetures de périodes.
"""

import hashlib
import json
import re
from copy import deepcopy
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .document_settings import validate_print_settings
from .models import (
    LANGUAGES,
    Account,
    AuditEvent,
    Company,
    Customer,
    Entry,
    EntryLine,
    IdempotencyRecord,
    Invoice,
    InvoiceLine,
    Journal,
    NumberSequence,
    Payment,
    Period,
    Product,
)

MAX_AMOUNT = Decimal("9999999999999999.999999")
MAX_QUANTITY = Decimal("9999999999.999999")


class DomainError(Exception):
    def __init__(self, code, detail=None):
        self.code = code
        self.detail = detail or code
        super().__init__(self.detail)


def _authorize(company, actor, roles):
    if actor is None or not actor.is_active or actor.company_id != company.pk or actor.role not in roles:
        raise DomainError("permission_denied")


def _lock(company):
    return Company.objects.select_for_update().get(pk=company.pk)


def _date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise DomainError("invalid_input") from None


def _decimal(value, *, places=6, minimum=Decimal("0"), maximum=MAX_AMOUNT, positive=False):
    if isinstance(value, (float, bool)) or not isinstance(value, (str, int, Decimal)):
        raise DomainError("invalid_amount")
    if isinstance(value, str) and not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        raise DomainError("invalid_amount")
    try:
        result = Decimal(value)
        if not result.is_finite() or result < minimum or result > maximum:
            raise DomainError("invalid_amount")
        if positive and result <= 0:
            raise DomainError("invalid_amount")
        if result != result.quantize(Decimal(1).scaleb(-places)):
            raise DomainError("invalid_amount")
        return result
    except InvalidOperation:
        raise DomainError("invalid_amount") from None


def _reference(model, company, value):
    identifier = getattr(value, "pk", value)
    try:
        result = model.objects.get(company=company, pk=identifier)
    except (model.DoesNotExist, TypeError, ValueError):
        raise DomainError("not_found") from None
    if result.archived:
        raise DomainError("archived_reference")
    return result


def _audit(company, actor, action, obj, metadata=None):
    return AuditEvent.objects.create(
        company=company, actor=actor, actor_name=actor.username if actor else "",
        action=action, object_type=obj._meta.model_name, object_id=str(obj.pk), metadata=metadata or {},
    )


def _period(company, posting_date):
    period = Period.objects.select_for_update().filter(company=company, start__lte=posting_date, end__gte=posting_date).first()
    if period is None:
        raise DomainError("period_missing")
    if period.closed:
        raise DomainError("period_closed")
    return period


def _fingerprint(action, invoice_id, payload):
    content = json.dumps({"action": action, "invoice": str(invoice_id), "payload": payload}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(content.encode()).hexdigest()


def _retry(company, invoice_id, key, action, payload):
    if not isinstance(key, str) or not key.strip() or len(key) > 128:
        raise DomainError("idempotency_required")
    fingerprint = _fingerprint(action, invoice_id, payload)
    previous = IdempotencyRecord.objects.filter(company=company, key=key).first()
    if previous and previous.fingerprint != fingerprint:
        raise DomainError("idempotency_conflict")
    return previous, fingerprint


def _remember(company, invoice, key, action, fingerprint):
    IdempotencyRecord.objects.create(company=company, invoice=invoice, key=key, action=action, fingerprint=fingerprint)


def _invoice(company, invoice_id):
    try:
        return Invoice.objects.select_for_update().select_related("customer", "company").get(company=company, pk=invoice_id)
    except Invoice.DoesNotExist:
        raise DomainError("not_found") from None


def _calculate(company, lines):
    if not isinstance(lines, list) or not lines or len(lines) > 200:
        raise DomainError("invalid_input")
    quantum = Decimal(1).scaleb(-company.precision)
    results = []
    with localcontext() as context:
        context.prec = 50
        for position, item in enumerate(lines):
            if not isinstance(item, dict):
                raise DomainError("invalid_input")
            description = item.get("description", "")
            if not isinstance(description, str) or not description.strip() or len(description) > 500:
                raise DomainError("invalid_input")
            product = _reference(Product, company, item["product"]) if item.get("product") is not None else None
            quantity = _decimal(item.get("quantity"), maximum=MAX_QUANTITY, positive=True)
            unit_price = _decimal(item.get("unit_price"))
            tax_rate = _decimal(item.get("tax_rate"), places=4, maximum=Decimal("100"))
            discount_rate = _decimal(item.get("discount_rate", "0"), places=4, maximum=Decimal("100"))
            net = (quantity * unit_price * (Decimal("1") - discount_rate / Decimal("100"))).quantize(quantum, rounding=ROUND_HALF_UP)
            tax = (net * tax_rate / Decimal("100")).quantize(quantum, rounding=ROUND_HALF_UP)
            if net + tax > MAX_AMOUNT:
                raise DomainError("invalid_amount")
            results.append(dict(position=position, product=product, description=description.strip(), quantity=quantity, unit_price=unit_price, tax_rate=tax_rate, discount_rate=discount_rate, net=net, tax=tax, total=net + tax))
    total = sum((line["total"] for line in results), Decimal("0"))
    if total > MAX_AMOUNT:
        raise DomainError("invalid_amount")
    return results


@transaction.atomic
def save_draft(company, actor, data, invoice_id=None):
    _authorize(company, actor, {"admin", "accountant", "sales"})
    text_fields = {"customer_reference": 200, "document_title": 150, "notes": 4000, "payment_terms": 2000, "shipping_address": 2000}
    if not isinstance(data, dict) or set(data) - {"customer", "issue_date", "due_date", "document_language", "lines", *text_fields}:
        raise DomainError("invalid_input")
    company = _lock(company)
    invoice = _invoice(company, invoice_id) if invoice_id else Invoice(company=company)
    if invoice.status != "draft":
        raise DomainError("immutable")
    invoice.customer = _reference(Customer, company, data.get("customer", invoice.customer_id))
    invoice.issue_date = _date(data.get("issue_date", invoice.issue_date))
    invoice.due_date = _date(data.get("due_date", invoice.due_date))
    if invoice.due_date < invoice.issue_date:
        raise DomainError("invalid_input")
    invoice.document_language = data.get("document_language", invoice.document_language if invoice.pk else company.document_language)
    if invoice.document_language not in dict(LANGUAGES):
        raise DomainError("invalid_input")
    for name, maximum in text_fields.items():
        value = data.get(name, getattr(invoice, name))
        if not isinstance(value, str) or len(value) > maximum:
            raise DomainError("invalid_input")
        setattr(invoice, name, value)
    source_lines = data.get("lines")
    if source_lines is None and invoice.pk:
        source_lines = list(invoice.lines.values("product", "description", "quantity", "unit_price", "tax_rate", "discount_rate"))
    lines = _calculate(company, source_lines)
    invoice.net = sum((line["net"] for line in lines), Decimal("0"))
    invoice.tax = sum((line["tax"] for line in lines), Decimal("0"))
    invoice.total = invoice.net + invoice.tax
    invoice.save()
    invoice.lines.all().delete()
    InvoiceLine.objects.bulk_create([InvoiceLine(company=company, invoice=invoice, **line) for line in lines])
    return invoice


def _entry(company, invoice, posting_date, kind, values, payment=None):
    period = _period(company, posting_date)
    try:
        journal = Journal.objects.get(company=company, code="SALES" if kind == "invoice" else "BANK")
    except Journal.DoesNotExist:
        raise DomainError("invalid_input") from None
    accounts = {account.kind: account for account in Account.objects.filter(company=company)}
    filtered = [(account, debit, credit) for account, debit, credit in values if debit or credit]
    debit = sum((value[1] for value in filtered), Decimal("0"))
    credit = sum((value[2] for value in filtered), Decimal("0"))
    if len(filtered) < 2 or debit <= 0 or debit != credit or any(account not in accounts for account, _, _ in filtered):
        raise DomainError("invalid_amount")
    entry = Entry.objects.create(company=company, invoice=invoice, payment=payment, date=posting_date, reference=invoice.number, journal=journal, period=period, kind=kind)
    EntryLine.objects.bulk_create([EntryLine(company=company, entry=entry, account=accounts[account], debit=debit, credit=credit) for account, debit, credit in filtered])
    return entry


def _snapshot(invoice, lines=None):
    company, customer = invoice.company, invoice.customer
    precision = invoice.precision if invoice.precision is not None else company.precision
    source_lines = lines if lines is not None else invoice.lines.select_related("product").all()

    def money(value):
        return format(value, f".{precision}f")

    return {
        "company": {"name": company.name, "address": company.address, "email": company.email, "currency": company.currency},
        "customer": {"name": customer.name, "address": customer.address, "email": customer.email, "tax_id": customer.tax_id},
        "number": invoice.number, "issue_date": invoice.issue_date.isoformat(), "due_date": invoice.due_date.isoformat(),
        "document_language": invoice.document_language, "currency": invoice.currency or company.currency, "precision": precision, "locale": company.locale,
        "status": invoice.status,
        "customer_reference": invoice.customer_reference, "document_title": invoice.document_title,
        "notes": invoice.notes, "payment_terms": invoice.payment_terms, "shipping_address": invoice.shipping_address,
        "print_settings": deepcopy(company.print_settings),
        "rounding": {"mode": "ROUND_HALF_UP", "scope": "line", "tax_base": "rounded_net"},
        "lines": [{"description": line.description, "product_reference": line.product.reference if line.product else "", "quantity": format(line.quantity, "f"), "unit_price": format(line.unit_price, "f"), "tax_rate": format(line.tax_rate, "f"), "discount_rate": format(line.discount_rate, "f"), "net": money(line.net), "tax": money(line.tax), "total": money(line.total)} for line in source_lines],
        "net": money(invoice.net), "tax": money(invoice.tax), "total": money(invoice.total), "demo": True,
    }


@transaction.atomic
def preview_invoice(company, actor, invoice_id):
    """Recalcul transitoire, sans modifier le brouillon ni les instantanés validés."""
    _authorize(company, actor, {"admin", "accountant", "sales", "viewer"})
    company = _lock(company)
    invoice = _invoice(company, invoice_id)
    if invoice.status == "validated":
        return invoice.snapshot
    source = list(invoice.lines.values("product", "description", "quantity", "unit_price", "tax_rate", "discount_rate"))
    calculated = _calculate(company, source)
    lines = [InvoiceLine(company=company, invoice=invoice, **line) for line in calculated]
    invoice.net = sum((line.net for line in lines), Decimal("0"))
    invoice.tax = sum((line.tax for line in lines), Decimal("0"))
    invoice.total = invoice.net + invoice.tax
    return _snapshot(invoice, lines=lines)


@transaction.atomic
def duplicate_invoice(company, actor, invoice_id, key, data):
    _authorize(company, actor, {"admin", "accountant", "sales"})
    if not isinstance(data, dict) or set(data) != {"issue_date", "due_date"}:
        raise DomainError("invalid_input")
    company = _lock(company)
    original = _invoice(company, invoice_id)
    dates = {name: _date(value) for name, value in data.items()}
    previous, fingerprint = _retry(company, invoice_id, key, "duplicate", dates)
    if previous:
        return _invoice(company, previous.invoice_id)
    data = {**dates, "customer": original.customer_id, "document_language": original.document_language}
    data.update({name: getattr(original, name) for name in ("customer_reference", "document_title", "notes", "payment_terms", "shipping_address")})
    data["lines"] = list(original.lines.values("product", "description", "quantity", "unit_price", "tax_rate", "discount_rate"))
    invoice = save_draft(company, actor, data)
    _audit(company, actor, "invoice.duplicated", invoice, {"source_invoice": original.pk})
    _remember(company, invoice, key, "duplicate", fingerprint)
    return invoice


@transaction.atomic
def validate_invoice(company, actor, invoice_id, key, payload=None):
    _authorize(company, actor, {"admin", "accountant"})
    company = _lock(company)
    invoice = _invoice(company, invoice_id)
    payload = payload if payload is not None else {}
    if not isinstance(payload, dict):
        raise DomainError("invalid_input")
    previous, fingerprint = _retry(company, invoice_id, key, "validate", payload)
    if previous:
        return invoice
    if payload:
        raise DomainError("invalid_input")
    if invoice.status != "draft":
        raise DomainError("already_validated")
    # Recalcul autoritaire avec la précision actuelle : un brouillon peut avoir
    # été créé avant une modification de configuration.
    invoice = save_draft(company, actor, {}, invoice_id=invoice_id)
    if invoice.total <= 0:
        raise DomainError("invalid_amount")
    _period(company, invoice.issue_date)
    sequence, _ = NumberSequence.objects.select_for_update().get_or_create(company=company, year=invoice.issue_date.year)
    invoice.number = f"INV-{sequence.year}-{sequence.next_value:06d}"
    sequence.next_value += 1
    sequence.save(update_fields=["next_value"])
    invoice.status = "validated"
    invoice.precision = company.precision
    invoice.currency = company.currency
    invoice.validated_at = timezone.now()
    invoice.snapshot = _snapshot(invoice)
    invoice.save()
    zero = Decimal("0")
    _entry(company, invoice, invoice.issue_date, "invoice", [("receivable", invoice.total, zero), ("revenue", zero, invoice.net), ("tax", zero, invoice.tax)])
    _audit(company, actor, "invoice.validated", invoice, {"number": invoice.number, "total": format(invoice.total, "f"), "currency": invoice.currency})
    _remember(company, invoice, key, "validate", fingerprint)
    return invoice


@transaction.atomic
def record_payment(company, actor, invoice_id, key, data):
    _authorize(company, actor, {"admin", "accountant"})
    if not isinstance(data, dict) or set(data) - {"amount", "date", "reference"}:
        raise DomainError("invalid_input")
    company = _lock(company)
    invoice = _invoice(company, invoice_id)
    if invoice.status != "validated":
        raise DomainError("invalid_input")
    amount = _decimal(data.get("amount"), places=invoice.precision, positive=True)
    payment_date = _date(data.get("date"))
    reference = data.get("reference", "")
    if not isinstance(reference, str) or len(reference) > 200 or payment_date < invoice.issue_date:
        raise DomainError("invalid_input")
    payload = {"amount": format(amount, f".{invoice.precision}f"), "date": payment_date.isoformat(), "reference": reference}
    previous, fingerprint = _retry(company, invoice_id, key, "payment", payload)
    if previous:
        return invoice
    if amount > invoice.balance:
        raise DomainError("overpayment")
    _period(company, payment_date)
    payment = Payment.objects.create(company=company, invoice=invoice, amount=amount, date=payment_date, reference=reference)
    zero = Decimal("0")
    _entry(company, invoice, payment_date, "payment", [("bank", amount, zero), ("receivable", zero, amount)], payment=payment)
    _audit(company, actor, "payment.recorded", payment, {"invoice": invoice.pk, **payload})
    _remember(company, invoice, key, "payment", fingerprint)
    return invoice


@transaction.atomic
def configure_company(company, actor, data):
    _authorize(company, actor, {"admin"})
    company = _lock(company)
    allowed = {"name", "address", "email", "currency", "precision", "document_language", "locale", "print_settings"}
    if set(data) - allowed:
        raise DomainError("invalid_input")
    if any(field in data and data[field] != getattr(company, field) for field in ("currency", "precision")):
        # Import tardif : les connexions reposent elles-mêmes sur les services ERP.
        from connections.models import BankAccount, ExternalTransaction

        if (Invoice.objects.filter(company=company, status="validated").exists()
                or BankAccount.objects.filter(company=company).exists()
                or ExternalTransaction.objects.filter(company=company).exists()):
            raise DomainError("configuration_locked")
    for field, value in data.items():
        setattr(company, field, value)
    if not re.fullmatch(r"[A-Z]{3}", company.currency) or isinstance(company.precision, bool) or company.precision not in range(5):
        raise DomainError("invalid_input")
    try:
        validate_print_settings(company.print_settings)
        company.full_clean()
    except ValidationError:
        raise DomainError("invalid_input") from None
    company.save()
    _audit(company, actor, "company.updated", company, {"fields": sorted(data)})
    return company


@transaction.atomic
def set_period(company, actor, data, period_id=None):
    _authorize(company, actor, {"admin"})
    company = _lock(company)
    if set(data) - {"name", "start", "end", "closed"}:
        raise DomainError("invalid_input")
    if period_id:
        try:
            period = Period.objects.select_for_update().get(company=company, pk=period_id)
        except Period.DoesNotExist:
            raise DomainError("not_found") from None
    else:
        period = Period(company=company)
    start = _date(data.get("start", period.start))
    end = _date(data.get("end", period.end))
    if start > end:
        raise DomainError("invalid_input")
    if period.pk and Entry.objects.filter(period=period).exists() and (start != period.start or end != period.end):
        raise DomainError("immutable")
    if Period.objects.filter(company=company, start__lte=end, end__gte=start).exclude(pk=period.pk).exists():
        raise DomainError("invalid_input")
    period.start, period.end = start, end
    period.name = data.get("name", period.name)
    period.closed = data.get("closed", period.closed)
    if not isinstance(period.name, str) or not period.name.strip() or len(period.name) > 100 or not isinstance(period.closed, bool):
        raise DomainError("invalid_input")
    period.save()
    _audit(company, actor, "period.updated" if period_id else "period.created", period, {"closed": period.closed, "start": start.isoformat(), "end": end.isoformat()})
    return period


@transaction.atomic
def bootstrap_company(company):
    company = _lock(company)
    for code, name, kind in [("1100", "Clients (démonstration)", "receivable"), ("4000", "Ventes (démonstration)", "revenue"), ("2100", "Taxe collectée (démonstration)", "tax"), ("1000", "Banque (démonstration)", "bank")]:
        Account.objects.get_or_create(company=company, kind=kind, defaults={"code": code, "name": name})
    for code, name in [("SALES", "Ventes (démonstration)"), ("BANK", "Banque (démonstration)")]:
        Journal.objects.get_or_create(company=company, code=code, defaults={"name": name})
