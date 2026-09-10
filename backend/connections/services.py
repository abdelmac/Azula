"""Imports sans appel bancaire ; écritures comptables exclusivement sur confirmation."""

import csv
import hashlib
import io
import json
import secrets
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import ValidationError

from erp.models import Company, Invoice, Payment
from erp.services import MAX_AMOUNT, DomainError, _audit, _authorize, _decimal, record_payment

from .auth import assert_key_active
from .models import BankAccount, BankTransaction, ExternalRequest, ExternalTransaction, Integration, IntegrationKey


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@transaction.atomic
def issue_key(company, actor, data):
    _authorize(company, actor, {"admin"})
    Company.objects.select_for_update().get(pk=company.pk)
    try:
        integration = Integration.objects.get(company=company, pk=data["integration"], enabled=True)
    except Integration.DoesNotExist:
        raise DomainError("not_found") from None
    secret = "azula_" + secrets.token_urlsafe(32)
    key = IntegrationKey.objects.create(company=company, integration=integration, creator=actor,
        name=data["name"], scopes=data["scopes"], expires_at=data["expires_at"], prefix=secret[:14],
        digest=hashlib.sha256(secret.encode()).hexdigest())
    _audit(company, actor, "integration.key_created", key, {"integration": integration.pk, "scopes": key.scopes})
    return key, secret


@transaction.atomic
def external_write(key, action, idempotency_key, payload, operation):
    company = Company.objects.select_for_update().get(pk=key.company_id)
    key = IntegrationKey.objects.select_related("creator", "integration").get(pk=key.pk)
    assert_key_active(key, action.split("/", 1)[0])
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 128:
        raise DomainError("idempotency_required")
    digest = fingerprint({"action": action, "payload": payload})
    previous = ExternalRequest.objects.filter(company=company, integration=key.integration, key=idempotency_key).first()
    if previous:
        if previous.fingerprint != digest or previous.action != action:
            raise DomainError("idempotency_conflict")
        return previous.response, True
    result = operation(company, key.creator)
    # Le JSON stocké a exactement les mêmes types que la réponse initiale.
    result = json.loads(json.dumps(result, default=str))
    ExternalRequest.objects.create(company=company, integration=key.integration, key=idempotency_key,
        action=action, fingerprint=digest, response=result)
    _audit(company, key.creator, "integration.request", key.integration, {"action": action})
    return result, False


def receive_transaction(company, integration, data):
    if data["currency"] != company.currency:
        raise DomainError("invalid_input")
    previous = ExternalTransaction.objects.filter(company=company, integration=integration, external_id=data["external_id"]).first()
    if previous:
        if any(getattr(previous, name) != value for name, value in data.items()):
            raise DomainError("idempotency_conflict")
        return previous
    return ExternalTransaction.objects.create(company=company, integration=integration, **data)


def parse_csv(content):
    if not isinstance(content, str) or not content or len(content.encode("utf-8")) > 250000:
        raise ValidationError("invalid_input")
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), strict=True)
    required = {"external_id", "date", "amount", "description"}
    try:
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or not required.issubset(fields) or set(fields) - required - {"reference"}:
            raise ValidationError("invalid_input")
        result, seen = [], set()
        for row in reader:
            if len(result) >= 500 or None in row or any(value is None for value in row.values()):
                raise ValidationError("invalid_input")
            identifier = row["external_id"].strip()
            if not identifier or len(identifier) > 128 or identifier in seen:
                raise ValidationError("invalid_input")
            seen.add(identifier)
            amount = _decimal(row["amount"], minimum=-MAX_AMOUNT)
            if amount == Decimal("0"):
                raise DomainError("invalid_amount")
            if len(row["description"]) > 500 or len(row.get("reference", "")) > 200:
                raise ValidationError("invalid_input")
            posting_date = date.fromisoformat(row["date"])
            if posting_date.isoformat() != row["date"]:
                raise ValidationError("invalid_input")
            result.append({"external_id": identifier, "date": posting_date.isoformat(), "amount": format(amount, ".6f"),
                "description": row["description"], "reference": row.get("reference", "")})
        if not result:
            raise ValidationError("invalid_input")
        return result
    except (csv.Error, ValueError, OverflowError):
        raise ValidationError("invalid_input") from None


def _same_bank_row(previous, row):
    return (previous.date.isoformat() == row["date"] and previous.amount == Decimal(row["amount"])
            and previous.description == row["description"] and previous.reference == row["reference"])


@transaction.atomic
def import_bank_csv(company, actor, account_id, data):
    _authorize(company, actor, {"admin", "accountant"})
    Company.objects.select_for_update().get(pk=company.pk)
    try:
        account = BankAccount.objects.select_for_update().get(company=company, pk=account_id, archived=False)
    except BankAccount.DoesNotExist:
        raise DomainError("not_found") from None
    if account.currency != company.currency:
        raise DomainError("invalid_input")
    rows = parse_csv(data["csv"])
    digest = fingerprint({"account": account.pk, "currency": account.currency, "rows": rows})
    confirm = data.get("confirm", False)
    if confirm and data.get("preview_digest") != digest:
        raise DomainError("idempotency_conflict")
    previous = {obj.external_id: obj for obj in BankTransaction.objects.filter(company=company, account=account, external_id__in=[r["external_id"] for r in rows])}
    duplicates = 0
    for row in rows:
        existing = previous.get(row["external_id"])
        if existing:
            if not _same_bank_row(existing, row):
                raise DomainError("idempotency_conflict")
            duplicates += 1
    if confirm:
        BankTransaction.objects.bulk_create([BankTransaction(company=company, account=account, **row) for row in rows if row["external_id"] not in previous])
        _audit(company, actor, "bank.imported", account, {"created": len(rows) - duplicates, "duplicates": duplicates, "digest": digest})
    return {"rows": rows, "count": len(rows), "duplicates": duplicates, "created": len(rows) - duplicates if confirm else 0,
        "preview_digest": digest, "confirmed": confirm, "total": format(sum((Decimal(row["amount"]) for row in rows), Decimal("0")), ".6f")}


@transaction.atomic
def reconcile_bank_transaction(company, actor, transaction_id, invoice_id):
    _authorize(company, actor, {"admin", "accountant"})
    Company.objects.select_for_update().get(pk=company.pk)
    try:
        item = BankTransaction.objects.select_for_update().get(company=company, pk=transaction_id)
        invoice = Invoice.objects.get(company=company, pk=invoice_id)
    except (BankTransaction.DoesNotExist, Invoice.DoesNotExist):
        raise DomainError("not_found") from None
    if item.invoice_id:
        if item.invoice_id != invoice_id:
            raise DomainError("idempotency_conflict")
        return item
    account = BankAccount.objects.get(pk=item.account_id, company=company)
    if account.archived or item.amount <= 0 or invoice.status != "validated" or invoice.currency != account.currency:
        raise DomainError("invalid_input")
    reference = f"BANKTX-{item.pk}"
    # Le namespace HMAC ne peut pas être choisi par un appelant de l'API de règlement.
    payment_key = "bank:" + salted_hmac("connections.bank-payment", str(item.pk), algorithm="sha256").hexdigest()
    previous_id = Payment.objects.filter(company=company, invoice=invoice).aggregate(value=Max("id"))["value"] or 0
    record_payment(company, actor, invoice.pk, payment_key, {"amount": format(item.amount, "f"), "date": item.date.isoformat(), "reference": reference})
    payment = Payment.objects.get(company=company, invoice=invoice, pk__gt=previous_id)
    item.invoice = invoice
    item.payment = payment
    item.reconciled_at = timezone.now()
    item.save(update_fields=["invoice", "payment", "reconciled_at"])
    _audit(company, actor, "bank.reconciled", item, {"invoice": invoice.pk, "payment": payment.pk})
    return item
