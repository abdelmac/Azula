import re
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import (
    Account,
    AuditEvent,
    Company,
    Customer,
    Entry,
    EntryLine,
    Invoice,
    InvoiceLine,
    Journal,
    Payment,
    Period,
    Product,
    User,
)


class StrictInputMixin:
    """Refuse explicitement les champs inconnus et les champs internes."""

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("invalid_input")
        forbidden = set(data) - {name for name, field in self.fields.items() if not field.read_only}
        if forbidden:
            raise serializers.ValidationError({name: "invalid_input" for name in sorted(forbidden)})
        return super().to_internal_value(data)


class ExactDecimalField(serializers.DecimalField):
    def to_internal_value(self, data):
        if not isinstance(data, str) or not re.fullmatch(r"-?\d+(?:\.\d+)?", data):
            raise serializers.ValidationError("invalid_amount")
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError:
            raise serializers.ValidationError("invalid_amount") from None


class CompanySerializer(StrictInputMixin, serializers.ModelSerializer):
    currency = serializers.RegexField(r"^[A-Z]{3}$", max_length=3)
    precision = serializers.IntegerField(min_value=0, max_value=4)

    class Meta:
        model = Company
        fields = ("id", "name", "address", "email", "currency", "precision", "document_language", "locale")
        read_only_fields = ("id",)


class UserSerializer(StrictInputMixin, serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False, max_length=256)

    class Meta:
        model = User
        fields = ("id", "username", "role", "language", "is_active", "password")
        read_only_fields = ("id",)

    def validate(self, data):
        if self.instance is None and not data.get("password"):
            raise serializers.ValidationError({"password": "invalid_input"})
        if "password" in data:
            candidate = User(username=data.get("username", getattr(self.instance, "username", "")))
            validate_password(data["password"], candidate)
        return data


class MeSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "role", "language", "company")


class LanguageSerializer(StrictInputMixin, serializers.Serializer):
    language = serializers.ChoiceField(choices=("fr", "en", "ar", "de", "tr"))


class LoginSerializer(StrictInputMixin, serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


class CustomerSerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "address", "tax_id", "archived")
        read_only_fields = ("id",)


class ProductSerializer(StrictInputMixin, serializers.ModelSerializer):
    unit_price = ExactDecimalField(max_digits=22, decimal_places=6, min_value=Decimal("0"))
    tax_rate = ExactDecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0"), max_value=Decimal("100"))

    class Meta:
        model = Product
        fields = ("id", "reference", "name", "unit_price", "tax_rate", "archived")
        read_only_fields = ("id",)
        validators = []  # L'unicité est évaluée explicitement dans la société.


class DraftLineSerializer(StrictInputMixin, serializers.Serializer):
    product = serializers.IntegerField(min_value=1, allow_null=True, required=False, default=None)
    description = serializers.CharField(max_length=500)
    quantity = ExactDecimalField(max_digits=16, decimal_places=6, min_value=Decimal("0.000001"))
    unit_price = ExactDecimalField(max_digits=22, decimal_places=6, min_value=Decimal("0"))
    tax_rate = ExactDecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0"), max_value=Decimal("100"))


class DraftSerializer(StrictInputMixin, serializers.Serializer):
    customer = serializers.IntegerField(min_value=1)
    issue_date = serializers.DateField()
    due_date = serializers.DateField()
    document_language = serializers.ChoiceField(choices=("fr", "en", "ar", "de", "tr"))
    lines = DraftLineSerializer(many=True, allow_empty=False, max_length=200)


class PaymentInputSerializer(StrictInputMixin, serializers.Serializer):
    amount = ExactDecimalField(max_digits=22, decimal_places=6, min_value=Decimal("0.000001"))
    date = serializers.DateField()
    reference = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")


def money(value, precision):
    return format(value, f".{precision}f")


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = ("id", "product", "description", "quantity", "unit_price", "tax_rate", "net", "tax", "total")

    def to_representation(self, instance):
        result = super().to_representation(instance)
        precision = self.context.get("precision", 2)
        for field in ("net", "tax", "total"):
            result[field] = money(getattr(instance, field), precision)
        return result


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ("id", "amount", "date", "reference")

    def to_representation(self, instance):
        result = super().to_representation(instance)
        result["amount"] = money(instance.amount, self.context.get("precision", 2))
        return result


class InvoiceSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    paid = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ("id", "customer", "customer_name", "issue_date", "due_date", "document_language", "status", "number", "net", "tax", "total", "paid", "balance")

    def get_customer_name(self, obj):
        if hasattr(obj, "frozen_customer_name"):
            return obj.frozen_customer_name or obj.customer.name
        return obj.snapshot.get("customer", {}).get("name", obj.customer.name) if obj.snapshot else obj.customer.name

    def _paid(self, obj):
        if hasattr(obj, "paid_amount"):
            return obj.paid_amount
        return sum((payment.amount for payment in obj.payments.all()), Decimal("0"))

    def get_paid(self, obj):
        return money(self._paid(obj), obj.precision if obj.precision is not None else obj.company.precision)

    def get_balance(self, obj):
        return money(obj.total - self._paid(obj), obj.precision if obj.precision is not None else obj.company.precision)

    def to_representation(self, instance):
        result = super().to_representation(instance)
        precision = instance.precision if instance.precision is not None else instance.company.precision
        for field in ("net", "tax", "total"):
            result[field] = money(getattr(instance, field), precision)
        if self.context.get("detail", True):
            child_context = {**self.context, "precision": precision}
            result["lines"] = InvoiceLineSerializer(instance.lines.all(), many=True, context=child_context).data
            result["payments"] = PaymentSerializer(instance.payments.all(), many=True, context=child_context).data
            result["snapshot"] = instance.snapshot
        return result


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ("id", "code", "name", "kind")


class JournalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Journal
        fields = ("id", "code", "name")


class PeriodSerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = Period
        fields = ("id", "name", "start", "end", "closed")
        read_only_fields = ("id",)
        validators = []


class EntryLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)

    class Meta:
        model = EntryLine
        fields = ("account", "account_code", "debit", "credit")


class EntrySerializer(serializers.ModelSerializer):
    journal_code = serializers.CharField(source="journal.code", read_only=True)
    lines = EntryLineSerializer(many=True, read_only=True)
    total_debit = serializers.SerializerMethodField()
    total_credit = serializers.SerializerMethodField()

    class Meta:
        model = Entry
        fields = ("id", "date", "reference", "journal", "journal_code", "invoice", "lines", "total_debit", "total_credit")

    def get_total_debit(self, obj):
        return money(sum((line.debit for line in obj.lines.all()), Decimal("0")), obj.company.precision)

    def get_total_credit(self, obj):
        return money(sum((line.credit for line in obj.lines.all()), Decimal("0")), obj.company.precision)


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ("id", "created_at", "actor_name", "action", "object_type", "object_id", "metadata")
