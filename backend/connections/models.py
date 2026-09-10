from django.db import models
from django.db.models import Q

from erp.models import MONEY, CompanyOwned

SCOPES = (
    "catalog:read", "customers:read", "customers:write", "invoices:read",
    "invoices:write", "transactions:write", "banking:read",
)


class Integration(CompanyOwned):
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=20, choices=[(v, v) for v in ("website", "payments", "bank", "other")])
    provider = models.CharField(max_length=100, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class IntegrationKey(CompanyOwned):
    integration = models.ForeignKey(Integration, on_delete=models.PROTECT, related_name="keys")
    creator = models.ForeignKey("erp.User", on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=24)
    digest = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ExternalRequest(CompanyOwned):
    integration = models.ForeignKey(Integration, on_delete=models.PROTECT)
    key = models.CharField(max_length=128)
    action = models.CharField(max_length=80)
    fingerprint = models.CharField(max_length=64)
    response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "integration", "key"], name="external_request_unique_key")]


class ExternalTransaction(CompanyOwned):
    integration = models.ForeignKey(Integration, on_delete=models.PROTECT)
    external_id = models.CharField(max_length=128)
    amount = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=3)
    date = models.DateField()
    reference = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "integration", "external_id"], name="external_transaction_unique_id"),
            models.CheckConstraint(condition=~Q(amount=0), name="external_transaction_nonzero"),
        ]


class BankAccount(CompanyOwned):
    name = models.CharField(max_length=150)
    bank_name = models.CharField(max_length=150, blank=True)
    iban = models.CharField(max_length=34, blank=True)
    bic = models.CharField(max_length=11, blank=True)
    currency = models.CharField(max_length=3)
    archived = models.BooleanField(default=False)


class BankTransaction(CompanyOwned):
    account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="transactions")
    external_id = models.CharField(max_length=128)
    date = models.DateField()
    amount = models.DecimalField(**MONEY)
    description = models.CharField(max_length=500, blank=True)
    reference = models.CharField(max_length=200, blank=True)
    invoice = models.ForeignKey("erp.Invoice", on_delete=models.PROTECT, null=True, blank=True)
    payment = models.OneToOneField("erp.Payment", on_delete=models.PROTECT, null=True, blank=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "account", "external_id"], name="bank_transaction_unique_id"),
            models.CheckConstraint(condition=~Q(amount=0), name="bank_transaction_nonzero"),
            models.CheckConstraint(condition=Q(invoice__isnull=True, payment__isnull=True, reconciled_at__isnull=True) | Q(invoice__isnull=False, payment__isnull=False, reconciled_at__isnull=False), name="bank_transaction_reconciled_state"),
        ]
        indexes = [models.Index(fields=["company", "account", "-date", "-id"])]
