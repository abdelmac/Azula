import re
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from erp.serializers import ExactDecimalField, StrictInputMixin

from .models import SCOPES, BankAccount, BankTransaction, ExternalTransaction, Integration, IntegrationKey


class IntegrationSerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = Integration
        fields = ("id", "name", "kind", "provider", "enabled", "created_at")
        read_only_fields = ("id", "created_at")


class KeySerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationKey
        fields = ("id", "integration", "name", "prefix", "scopes", "expires_at", "revoked_at", "created_at")


class KeyInput(StrictInputMixin, serializers.Serializer):
    integration = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=100)
    scopes = serializers.ListField(child=serializers.ChoiceField(choices=SCOPES), min_length=1, max_length=len(SCOPES))
    expires_at = serializers.DateTimeField()

    def validate_expires_at(self, value):
        if value <= timezone.now() or value > timezone.now() + timezone.timedelta(days=366):
            raise serializers.ValidationError("invalid_input")
        return value

    def validate_scopes(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("invalid_input")
        return value


class BankAccountSerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ("id", "name", "bank_name", "iban", "bic", "currency", "archived")
        read_only_fields = ("id",)

    def validate_iban(self, value):
        value = value.replace(" ", "").upper()
        if value:
            if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", value):
                raise serializers.ValidationError("invalid_input")
            digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in value[4:] + value[:4])
            if int(digits) % 97 != 1:
                raise serializers.ValidationError("invalid_input")
        return value

    def validate_bic(self, value):
        value = value.strip().upper()
        if value and not re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?", value):
            raise serializers.ValidationError("invalid_input")
        return value

    def validate_currency(self, value):
        if value != self.context["request"].user.company.currency:
            raise serializers.ValidationError("invalid_input")
        return value


class BankTransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default="")

    class Meta:
        model = BankTransaction
        fields = ("id", "account", "account_name", "external_id", "date", "amount", "description", "reference", "invoice", "invoice_number", "payment", "reconciled_at")


class ExternalTransactionSerializer(serializers.ModelSerializer):
    integration_name = serializers.CharField(source="integration.name", read_only=True)
    status = serializers.SerializerMethodField()

    def get_status(self, obj):
        return "received"

    class Meta:
        model = ExternalTransaction
        fields = ("id", "integration", "integration_name", "external_id", "amount", "currency", "date", "reference", "status", "created_at")


class TransactionInput(StrictInputMixin, serializers.Serializer):
    external_id = serializers.CharField(max_length=128)
    amount = ExactDecimalField(max_digits=22, decimal_places=6)
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    date = serializers.DateField()
    reference = serializers.CharField(max_length=200, allow_blank=True, default="")

    def validate_amount(self, value):
        if value == Decimal("0"):
            raise serializers.ValidationError("invalid_amount")
        return value


class CsvInput(StrictInputMixin, serializers.Serializer):
    csv = serializers.CharField(max_length=250000, trim_whitespace=False)
    confirm = serializers.BooleanField(default=False)
    preview_digest = serializers.RegexField(r"^[a-f0-9]{64}$", required=False)


class ReconcileInput(StrictInputMixin, serializers.Serializer):
    invoice = serializers.IntegerField(min_value=1)
    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("invalid_input")
        return value
