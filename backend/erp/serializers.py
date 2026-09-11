import re
from decimal import Decimal
from urllib.parse import urlsplit

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .document_settings import validate_print_settings
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
    ProductCategory,
    Unit,
    User,
    Warehouse,
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
    def validate_empty_values(self, data):
        # DRF assimile normalement une chaîne vide à null pour les décimaux
        # facultatifs ; l'API exige ici un null JSON explicite.
        if self.allow_null and isinstance(data, str) and not data.strip():
            raise serializers.ValidationError("invalid_amount")
        return super().validate_empty_values(data)

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
        fields = ("id", "name", "address", "email", "currency", "precision", "document_language", "locale", "print_settings")
        read_only_fields = ("id",)

    def validate_print_settings(self, value):
        return validate_print_settings(value)


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
    billing = serializers.SerializerMethodField()

    def get_billing(self, user):
        from billing.access import get_access

        return get_access(user.company_id)

    class Meta:
        model = User
        fields = ("id", "username", "role", "language", "company", "billing")


class LanguageSerializer(StrictInputMixin, serializers.Serializer):
    language = serializers.ChoiceField(choices=("fr", "en", "ar", "de", "tr"))


class LoginSerializer(StrictInputMixin, serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


def validate_custom_fields(value):
    if not isinstance(value, dict) or len(value) > 20:
        raise serializers.ValidationError("invalid_input")
    for key, content in value.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 60 or not isinstance(content, str) or len(content) > 500:
            raise serializers.ValidationError("invalid_input")
        if any(char in key + content for char in "<>"):
            raise serializers.ValidationError("invalid_input")
    return value


class CustomerSerializer(StrictInputMixin, serializers.ModelSerializer):
    default_discount_rate = ExactDecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0"), max_value=Decimal("100"), required=False)
    credit_limit = ExactDecimalField(max_digits=22, decimal_places=6, min_value=Decimal("0"), allow_null=True, required=False)
    country = serializers.RegexField(r"^[A-Z]{2}$", allow_blank=True, required=False)
    payment_terms_days = serializers.IntegerField(min_value=0, max_value=365, required=False)
    custom_fields = serializers.JSONField(required=False, validators=[validate_custom_fields])

    class Meta:
        model = Customer
        fields = (
            "id", "name", "email", "address", "tax_id", "archived", "reference", "legal_name", "latin_name",
            "contact_name", "phone", "phone_alt", "mobile", "fax", "website", "postal_code", "city", "region", "country",
            "shipping_address", "group_name", "payment_terms_days", "default_discount_rate", "credit_limit", "bank_name", "iban", "bic", "notes", "custom_fields",
        )
        read_only_fields = ("id",)
        validators = []
        extra_kwargs = {"address": {"max_length": 2000}}

    def validate_iban(self, value):
        value = value.replace(" ", "").upper()
        if value:
            if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", value):
                raise serializers.ValidationError("invalid_input")
            digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in value[4:] + value[:4])
            if int(digits) % 97 != 1:
                raise serializers.ValidationError("invalid_input")
        return value

    def validate_bic(self, value):
        value = value.replace(" ", "").upper()
        if value and not re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?", value):
            raise serializers.ValidationError("invalid_input")
        return value

    def validate_website(self, value):
        if value:
            url = urlsplit(value)
            if url.scheme not in {"https", "http"} or url.username is not None or url.password is not None:
                raise serializers.ValidationError("invalid_input")
        return value


class CatalogReferenceSerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        fields = ("id", "code", "name", "archived")
        read_only_fields = ("id",)
        validators = []  # L'unicité est contrôlée sous verrou dans la société.


class ProductCategorySerializer(CatalogReferenceSerializer):
    class Meta(CatalogReferenceSerializer.Meta):
        model = ProductCategory


class WarehouseSerializer(CatalogReferenceSerializer):
    class Meta(CatalogReferenceSerializer.Meta):
        model = Warehouse


class UnitSerializer(CatalogReferenceSerializer):
    class Meta(CatalogReferenceSerializer.Meta):
        model = Unit


class ProductSerializer(StrictInputMixin, serializers.ModelSerializer):
    weight = ExactDecimalField(max_digits=16, decimal_places=6, min_value=Decimal("0"), allow_null=True, required=False)
    custom_fields = serializers.JSONField(required=False, validators=[validate_custom_fields])
    unit_price = ExactDecimalField(max_digits=22, decimal_places=6, min_value=Decimal("0"))
    purchase_price = ExactDecimalField(max_digits=22, decimal_places=6, min_value=Decimal("0"), allow_null=True, required=False)
    tax_rate = ExactDecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0"), max_value=Decimal("100"))
    category = serializers.PrimaryKeyRelatedField(queryset=ProductCategory.objects.none(), allow_null=True, required=False)
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.none(), allow_null=True, required=False)
    warehouses = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.none(), many=True, required=False)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    unit_name = serializers.CharField(source="unit.name", read_only=True, default=None)

    class Meta:
        model = Product
        fields = (
            "id", "reference", "name", "unit_price", "purchase_price", "tax_rate", "archived",
            "category", "category_name", "unit", "unit_name", "warehouses", "specifications", "image_url",
            "latin_name", "barcode", "manufacturer", "supplier_name", "color", "dimensions", "origin", "weight", "notes", "custom_fields",
        )
        read_only_fields = ("id",)
        validators = []  # L'unicité est évaluée explicitement dans la société.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        company_id = getattr(getattr(request, "user", None), "company_id", None)
        for name, model in (("category", ProductCategory), ("unit", Unit), ("warehouses", Warehouse)):
            field = self.fields[name]
            if name == "warehouses":
                field = field.child_relation
            field.queryset = model.objects.filter(company_id=company_id)

    def validate(self, data):
        self.validate_catalog_relations(data)
        return data

    def validate_image_url(self, value):
        if value:
            url = urlsplit(value)
            if url.scheme != "https" or url.username is not None or url.password is not None:
                raise serializers.ValidationError("invalid_input")
        return value

    def validate_catalog_relations(self, data):
        """Rejoué sous verrou société pour vérifier l'état courant des références."""
        company_id = self.context["request"].user.company_id
        for name, model in (("category", ProductCategory), ("unit", Unit), ("warehouses", Warehouse)):
            if name not in data:
                continue
            values = data[name] if name == "warehouses" else [data[name]] if data[name] else []
            requested_ids = {value.pk for value in values}
            if not requested_ids:
                continue
            allowed = model.objects.filter(company_id=company_id, pk__in=requested_ids)
            current = set()
            if self.instance:
                current = set(self.instance.warehouses.values_list("id", flat=True)) if name == "warehouses" else {getattr(self.instance, name + "_id")}
            if allowed.count() != len(requested_ids) or allowed.filter(archived=True).exclude(pk__in=current).exists():
                raise serializers.ValidationError({name: "invalid_input"})


class DraftLineSerializer(StrictInputMixin, serializers.Serializer):
    discount_rate = ExactDecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0"), max_value=Decimal("100"), required=False, default=Decimal("0"))
    product = serializers.IntegerField(min_value=1, allow_null=True, required=False, default=None)
    description = serializers.CharField(max_length=500)
    quantity = ExactDecimalField(max_digits=16, decimal_places=6, min_value=Decimal("0.000001"))
    unit_price = ExactDecimalField(max_digits=22, decimal_places=6, min_value=Decimal("0"))
    tax_rate = ExactDecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0"), max_value=Decimal("100"))


class DraftSerializer(StrictInputMixin, serializers.Serializer):
    customer_reference = serializers.CharField(max_length=200, allow_blank=True, required=False)
    document_title = serializers.CharField(max_length=150, allow_blank=True, required=False)
    notes = serializers.CharField(max_length=4000, allow_blank=True, required=False)
    payment_terms = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    shipping_address = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    customer = serializers.IntegerField(min_value=1)
    issue_date = serializers.DateField()
    due_date = serializers.DateField()
    document_language = serializers.ChoiceField(choices=("fr", "en", "ar", "de", "tr"))
    lines = DraftLineSerializer(many=True, allow_empty=False, max_length=200)


class DuplicateInvoiceSerializer(StrictInputMixin, serializers.Serializer):
    issue_date = serializers.DateField()
    due_date = serializers.DateField()


class PaymentInputSerializer(StrictInputMixin, serializers.Serializer):
    amount = ExactDecimalField(max_digits=22, decimal_places=6, min_value=Decimal("0.000001"))
    date = serializers.DateField()
    reference = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")


def money(value, precision):
    return format(value, f".{precision}f")


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = ("id", "product", "description", "quantity", "unit_price", "tax_rate", "discount_rate", "net", "tax", "total")

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
        fields = ("id", "customer", "customer_name", "issue_date", "due_date", "document_language", "status", "number", "net", "tax", "total", "paid", "balance", "customer_reference", "document_title", "notes", "payment_terms", "shipping_address")

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
